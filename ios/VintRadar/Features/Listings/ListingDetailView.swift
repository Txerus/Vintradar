import Charts
import SwiftUI

struct ListingDetailView: View {
    @Environment(AppModel.self) private var model
    let item: ListingDTO
    @State private var history: [ListingSnapshotDTO] = []
    @State private var pricing: PricingDTO?
    @State private var showCorrection = false
    @State private var correctedKey = ""

    private var score: DealScore { model.score(for: item) }
    private var comparablePrices: [Double] { pricing?.comparables.map(\.totalItemPrice).sorted() ?? [] }
    private var galleryURLs: [URL] {
        let storedImages = item.imageUrls ?? []
        let values = storedImages.isEmpty ? [item.imageUrl].compactMap { $0 } : storedImages
        return values.compactMap(URL.init).reduce(into: []) { result, url in
            if !result.contains(url) { result.append(url) }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                heroImage
                VStack(alignment: .leading, spacing: 20) {
                    header
                    priceBreakdown
                    scoreSection
                    marketChart
                    comparablesSection
                    historySection
                    detailsSection
                    descriptionSection
                    sellerSection
                    actions
                }
                .padding(.horizontal)
                .padding(.bottom, 30)
            }
            .frame(maxWidth: 850)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle("Annonce")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await model.setFavorite(item) }
                } label: {
                    Image(systemName: model.flags[item.id]?.favorite == true ? "heart.fill" : "heart")
                }
                .accessibilityLabel(model.flags[item.id]?.favorite == true ? "Retirer des favoris" : "Ajouter aux favoris")
            }
        }
        .task {
            await model.setSeen(item)
            async let loadedHistory = model.history(for: item)
            async let loadedPricing = model.pricing(for: item)
            history = await loadedHistory
            pricing = await loadedPricing
        }
        .sheet(isPresented: $showCorrection) { correctionSheet }
    }

    private var heroImage: some View {
        Group {
            if galleryURLs.isEmpty {
                ContentUnavailableView("Image indisponible", systemImage: "photo")
            } else {
                TabView {
                    ForEach(galleryURLs, id: \.absoluteString) { url in
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .success(let image): image.resizable().scaledToFit()
                            case .failure: ContentUnavailableView("Image indisponible", systemImage: "photo")
                            default: ProgressView().frame(maxWidth: .infinity, minHeight: 280)
                            }
                        }
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: galleryURLs.count > 1 ? .automatic : .never))
            }
        }
        .frame(maxWidth: .infinity, minHeight: 280, maxHeight: 520)
        .background(.quaternary)
        .clipped()
        .accessibilityLabel("Photo de \(item.title)")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            ScoreBadge(score: score)
            Text(item.title).font(.title.bold())
            Text(item.total, format: .currency(code: item.currency))
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
            Text("Détectée \(item.firstSeenAt.formatted(.relative(presentation: .named)))")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var priceBreakdown: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Prix total estimé").font(.headline)
            LabeledContent("Article", value: item.price.formatted(.currency(code: item.currency)))
            LabeledContent("Livraison estimée", value: item.shippingEstimate.formatted(.currency(code: item.currency)))
            LabeledContent("Protection acheteur", value: item.buyerFee.formatted(.currency(code: item.currency)))
            Divider()
            LabeledContent("Total", value: item.total.formatted(.currency(code: item.currency))).fontWeight(.semibold)
        }
        .padding()
        .glassEffect(.regular, in: .rect(cornerRadius: 22))
    }

    private var scoreSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Pourquoi ce prix ?", systemImage: "info.circle.fill").font(.headline)
            Text(pricing.map { PricingPhrase.french($0.explanation, currency: item.currency) } ?? "Chargement de l’explication…")
                .foregroundStyle(.secondary)
            if let product = pricing?.explanation.product, let key = product.key {
                Button {
                    correctedKey = key
                    showCorrection = true
                } label: {
                    Label("Produit reconnu : \(product.model ?? key)", systemImage: "checkmark.seal")
                }
                .buttonStyle(.bordered)
            }
            Text("Les sources externes éventuelles sont indicatives et restent séparées de la médiane Vinted.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            ForEach(pricing?.explanation.externalReferences ?? [], id: \.self) { reference in
                if let value = reference.value {
                    LabeledContent(externalSourceName(reference.source)) {
                        Text(value, format: .currency(code: reference.currency ?? "EUR"))
                    }
                    .font(.subheadline)
                }
            }
        }
        .padding()
        .background(score.label.color.opacity(0.09), in: RoundedRectangle(cornerRadius: 22))
    }

    @ViewBuilder private var comparablesSection: some View {
        if let comparables = pricing?.comparables, !comparables.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("Annonces comparables").font(.headline)
                ForEach(comparables) { comparable in
                    if let url = URL(string: comparable.url) {
                        Link(destination: url) {
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(comparable.title).lineLimit(2)
                                    Text(comparable.condition ?? "État non précisé")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(comparable.totalItemPrice, format: .currency(code: item.currency))
                                    .fontWeight(.semibold)
                            }
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder private var marketChart: some View {
        if comparablePrices.count >= 3 {
            VStack(alignment: .leading, spacing: 12) {
                Text("Comparables").font(.headline)
                Chart {
                    if let p20 = pricing?.explanation.p20 {
                        RectangleMark(
                            xStart: .value("Début", 0),
                            xEnd: .value("Fin", comparablePrices.count + 1),
                            yStart: .value("Bas", 0),
                            yEnd: .value("Zone affaire", p20)
                        )
                        .foregroundStyle(.green.opacity(0.12))
                    }
                    ForEach(Array(comparablePrices.enumerated()), id: \.offset) { index, price in
                        PointMark(x: .value("Annonce", index + 1), y: .value("Prix", price))
                            .foregroundStyle(VintTheme.brand.opacity(0.65))
                    }
                    RuleMark(y: .value("Cette annonce", item.total))
                        .foregroundStyle(VintTheme.accent)
                        .lineStyle(StrokeStyle(lineWidth: 3))
                        .annotation(position: .top, alignment: .leading) { Text("Cette annonce").font(.caption.bold()) }
                    if let median = pricing?.explanation.median {
                        RuleMark(y: .value("Médiane", median))
                            .foregroundStyle(.secondary)
                            .lineStyle(StrokeStyle(dash: [5, 4]))
                    }
                }
                .frame(height: 210)
            }
        }
    }

    @ViewBuilder private var historySection: some View {
        if !history.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("Historique du prix").font(.headline)
                Chart(history) { snapshot in
                    LineMark(x: .value("Date", snapshot.observedAt), y: .value("Prix", snapshot.price))
                        .foregroundStyle(VintTheme.brand)
                    PointMark(x: .value("Date", snapshot.observedAt), y: .value("Prix", snapshot.price))
                        .foregroundStyle(VintTheme.accent)
                }
                .frame(height: 180)
            }
        }
    }

    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Caractéristiques").font(.headline)
            LabeledContent("État", value: item.condition ?? "Non précisé")
            LabeledContent("Taille", value: item.size ?? "Non précisée")
            LabeledContent("Marque", value: item.brand ?? "Non précisée")
            LabeledContent("Catégorie", value: item.categoryPath?.joined(separator: " › ") ?? item.categoryName ?? "Non précisée")
            LabeledContent("Couleurs", value: item.colors?.joined(separator: ", ") ?? "Non précisées")
            if let date = item.publishedAt { LabeledContent("Mise en ligne", value: date.formatted()) }
            if let favorites = item.favouriteCount { LabeledContent("Favoris", value: "\(favorites)") }
            if let views = item.viewCount { LabeledContent("Vues", value: "\(views)") }
            if let signal = InterestSignal.text(history: history, currentFavorites: item.favouriteCount) {
                Label(signal, systemImage: "arrow.up.right")
                    .foregroundStyle(.orange)
            }
            LabeledContent("Statut", value: statusLabel)
            LabeledContent("Référence", value: item.externalId)
        }
        .padding()
        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 22))
    }

    @ViewBuilder private var descriptionSection: some View {
        if !item.description.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Description").font(.headline)
                Text(item.description).textSelection(.enabled)
            }
        }
    }

    private var sellerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Vendeur").font(.headline)
            if let sellerName = item.sellerName {
                Label(sellerName, systemImage: "person.crop.circle.fill")
                if let rating = item.sellerRating {
                    LabeledContent("Évaluation", value: rating.formatted(.number.precision(.fractionLength(1))))
                }
                if let reviews = item.sellerReviewsCount {
                    LabeledContent("Avis", value: "\(reviews)")
                }
                if let location = item.sellerLocation { LabeledContent("Localisation", value: location) }
                if let since = item.sellerCreatedAt { LabeledContent("Membre depuis", value: since.formatted(.dateTime.year().month())) }
                if let lastLogin = item.sellerLastLoginAt { LabeledContent("Dernière connexion", value: lastLogin.formatted(.relative(presentation: .named))) }
            } else {
                Label("Informations non fournies pour cette annonce.", systemImage: "person.crop.circle.badge.questionmark")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            if let url = URL(string: "https://www.vinted.fr/items/\(item.externalId)") {
                Link(destination: url) {
                    Label("Voir l’annonce source", systemImage: "arrow.up.right.square")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
            Button(role: .destructive) {
                Task { await model.setHidden(item) }
            } label: {
                Label("Masquer cette annonce", systemImage: "eye.slash").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
        }
    }

    private var correctionSheet: some View {
        NavigationStack {
            Form {
                Section("Corriger le produit") {
                    TextField("Clé canonique", text: $correctedKey)
                    Button("Enregistrer la correction") {
                        Task {
                            if await model.correctProduct(item, key: correctedKey, exclude: false) {
                                pricing = await model.pricing(for: item)
                                showCorrection = false
                            }
                        }
                    }
                    Button("Exclure des statistiques", role: .destructive) {
                        Task {
                            if await model.correctProduct(item, key: nil, exclude: true) {
                                pricing = await model.pricing(for: item)
                                showCorrection = false
                            }
                        }
                    }
                }
            }
            .navigationTitle("Ce n’est pas le bon produit")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fermer") { showCorrection = false }
                }
            }
        }
    }

    private var statusLabel: String {
        switch item.status {
        case "ACTIVE": "Active"
        case "SOLD_CONFIRMED": "Vendue"
        case "DISAPPEARED": "Disparue"
        case "DELETED": "Supprimée"
        default: "Inconnu"
        }
    }

    private func externalSourceName(_ source: String) -> String {
        switch source {
        case "bricklink_sold_europe": "Ventes BrickLink Europe"
        case "brickset_retail": "Prix neuf officiel"
        case "pricecharting": "Référence indicative (marché US/PAL, USD converti)"
        default: source
        }
    }
}
