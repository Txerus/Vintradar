import Charts
import SwiftUI

struct ListingDetailView: View {
    private enum PricingState: Equatable {
        case loading
        case loaded
        case failed(String)
    }

    @Environment(AppModel.self) private var model
    let item: ListingDTO
    @State private var history: [ListingSnapshotDTO] = []
    @State private var pricing: PricingDTO?
    @State private var pricingState: PricingState = .loading
    @State private var enrichedItem: ListingDTO?
    @State private var enriching = false
    @State private var showCorrection = false
    @State private var correctedKey = ""

    private var score: DealScore { model.score(for: item) }
    private var comparablePrices: [Double] { pricing?.comparables.map(\.totalItemPrice).sorted() ?? [] }
    private var galleryURLs: [URL] {
        let displayed = enrichedItem ?? item
        let storedImages = displayed.imageUrls ?? []
        let values = storedImages.isEmpty ? [displayed.imageUrl].compactMap { $0 } : storedImages
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
            history = await model.history(for: item)
            await loadPricing()
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
            if score.label != .unknown {
                ScoreBadge(score: score)
            }
            Text(item.title).font(.title.bold())
            Text(FrenchFormat.currency(item.total, code: item.currency))
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
            Text("Détectée \(FrenchFormat.relative(item.firstSeenAt))")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var priceBreakdown: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Prix total estimé").font(.headline)
            LabeledContent("Article", value: FrenchFormat.currency(item.price, code: item.currency))
            LabeledContent("Livraison estimée", value: FrenchFormat.currency(item.shippingEstimate, code: item.currency))
            LabeledContent("Protection acheteur", value: FrenchFormat.currency(item.buyerFee, code: item.currency))
            Divider()
            LabeledContent("Total", value: FrenchFormat.currency(item.total, code: item.currency)).fontWeight(.semibold)
        }
        .padding()
        .glassEffect(.regular, in: .rect(cornerRadius: 22))
    }

    private var scoreSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Pourquoi ce prix ?", systemImage: "info.circle.fill").font(.headline)
            switch pricingState {
            case .loading:
                HStack {
                    ProgressView()
                    Text("Chargement de l’explication…")
                }
                .foregroundStyle(.secondary)
            case .loaded:
                Text(pricing.map { PricingPhrase.french($0.explanation, currency: item.currency) }
                     ?? "Prix non évalué : explication absente.")
                    .foregroundStyle(.secondary)
            case .failed(let reason):
                Label("Prix non évalué : \(reason)", systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.secondary)
                Button("Réessayer") { Task { await loadPricing(force: true) } }
                    .buttonStyle(.bordered)
            }
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
                        Text(FrenchFormat.currency(value, code: reference.currency ?? "EUR"))
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
                                Text(FrenchFormat.currency(comparable.totalItemPrice, code: item.currency))
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
        let displayed = enrichedItem ?? item
        VStack(alignment: .leading, spacing: 12) {
            Text("Caractéristiques").font(.headline)
            LabeledContent("État", value: displayed.condition ?? "Non précisé")
            LabeledContent("Taille", value: displayed.size ?? "Non précisée")
            LabeledContent("Marque", value: displayed.brand ?? "Non précisée")
            LabeledContent("Catégorie", value: displayed.categoryPath?.joined(separator: " › ") ?? displayed.categoryName ?? "Non précisée")
            LabeledContent("Couleurs", value: displayed.colors?.joined(separator: ", ") ?? "Non précisées")
            if let date = displayed.publishedAt {
                LabeledContent("Mise en ligne", value: FrenchFormat.dateTime(date))
            }
            if let favorites = displayed.favouriteCount { LabeledContent("Favoris", value: "\(favorites)") }
            if let views = displayed.viewCount { LabeledContent("Vues", value: "\(views)") }
            if let signal = InterestSignal.text(history: history, currentFavorites: displayed.favouriteCount) {
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
        let displayed = enrichedItem ?? item
        if !displayed.description.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Description").font(.headline)
                Text(displayed.description).textSelection(.enabled)
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                Text("Description").font(.headline)
                Label(
                    "Détails indisponibles : \(displayed.enrichmentError ?? "l’enrichissement n’a pas encore abouti").",
                    systemImage: "exclamationmark.triangle"
                )
                .foregroundStyle(.secondary)
                Button(enriching ? "Enrichissement…" : "Relancer l’enrichissement") {
                    Task { await retryEnrichment() }
                }
                .buttonStyle(.bordered)
                .disabled(enriching)
            }
        }
    }

    private var sellerSection: some View {
        let displayed = enrichedItem ?? item
        VStack(alignment: .leading, spacing: 8) {
            Text("Vendeur").font(.headline)
            if let sellerName = displayed.sellerName {
                Label(sellerName, systemImage: "person.crop.circle.fill")
                if let rating = displayed.sellerRating {
                    LabeledContent("Évaluation", value: rating.formatted(.number.precision(.fractionLength(1))))
                }
                if let reviews = displayed.sellerReviewsCount {
                    LabeledContent("Avis", value: "\(reviews)")
                }
                if let location = displayed.sellerLocation { LabeledContent("Localisation", value: location) }
                if let since = displayed.sellerCreatedAt { LabeledContent("Membre depuis", value: FrenchFormat.monthYear(since)) }
                if let lastLogin = displayed.sellerLastLoginAt { LabeledContent("Dernière connexion", value: FrenchFormat.relative(lastLogin)) }
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
                                await loadPricing(force: true)
                                showCorrection = false
                            }
                        }
                    }
                    Button("Exclure des statistiques", role: .destructive) {
                        Task {
                            if await model.correctProduct(item, key: nil, exclude: true) {
                                await loadPricing(force: true)
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

    @MainActor
    private func loadPricing(force: Bool = false) async {
        pricingState = .loading
        do {
            pricing = try await model.pricing(for: enrichedItem ?? item, force: force)
            pricingState = .loaded
        } catch {
            pricing = nil
            pricingState = .failed(error.localizedDescription)
        }
    }

    @MainActor
    private func retryEnrichment() async {
        enriching = true
        defer { enriching = false }
        do {
            enrichedItem = try await model.enrich(enrichedItem ?? item)
            await loadPricing(force: true)
        } catch {
            pricingState = .failed("Enrichissement impossible : \(error.localizedDescription)")
        }
    }
}
