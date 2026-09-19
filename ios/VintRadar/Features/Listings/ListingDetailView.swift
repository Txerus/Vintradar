import Charts
import SwiftUI

struct ListingDetailView: View {
    @Environment(AppModel.self) private var model
    let item: ListingDTO
    @State private var history: [ListingSnapshotDTO] = []

    private var score: DealScore { model.score(for: item) }
    private var comparablePrices: [Double] { model.comparablePrices(for: item).sorted() }
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
        }
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
            Text("Publiée \(item.createdAt.formatted(.relative(presentation: .named)))")
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
            Label("Pourquoi ce score ?", systemImage: "info.circle.fill").font(.headline)
            Text(score.explanation).foregroundStyle(.secondary)
            Text("Le score compare le prix total aux annonces de la même alerte. Il aide à décider, mais ne garantit ni l’état réel ni la disponibilité de l’article.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(score.label.color.opacity(0.09), in: RoundedRectangle(cornerRadius: 22))
    }

    @ViewBuilder private var marketChart: some View {
        if comparablePrices.count >= 3 {
            VStack(alignment: .leading, spacing: 12) {
                Text("Comparables").font(.headline)
                Chart {
                    ForEach(Array(comparablePrices.enumerated()), id: \.offset) { index, price in
                        PointMark(x: .value("Annonce", index + 1), y: .value("Prix", price))
                            .foregroundStyle(VintTheme.brand.opacity(0.65))
                    }
                    RuleMark(y: .value("Cette annonce", item.total))
                        .foregroundStyle(VintTheme.accent)
                        .lineStyle(StrokeStyle(lineWidth: 3))
                        .annotation(position: .top, alignment: .leading) { Text("Cette annonce").font(.caption.bold()) }
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
            } else {
                Label("Informations non fournies pour cette annonce.", systemImage: "person.crop.circle.badge.questionmark")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            if let url = URL(string: item.url) {
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

    private var statusLabel: String {
        switch item.status {
        case "ACTIVE": "Active"
        case "SOLD_CONFIRMED": "Vendue"
        case "DISAPPEARED": "Disparue"
        case "DELETED": "Supprimée"
        default: "Inconnu"
        }
    }
}
