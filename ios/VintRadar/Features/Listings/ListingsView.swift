import SwiftUI

struct ListingsView: View {
    enum SortMode: String, CaseIterable, Identifiable {
        case newest = "Plus récentes"
        case price = "Prix croissant"
        case score = "Meilleur score"
        var id: String { rawValue }
    }

    let title: String
    var alertID: Int?
    var favoritesOnly = false

    @Environment(AppModel.self) private var model
    @State private var query = ""
    @State private var sortMode: SortMode = .newest

    private var filtered: [ListingDTO] {
        var values = favoritesOnly ? model.favoriteListings : model.visibleListings
        if let alertID { values = values.filter { $0.alertIds?.contains(alertID) == true } }
        if !query.isEmpty { values = values.filter { $0.title.localizedCaseInsensitiveContains(query) } }
        switch sortMode {
        case .newest: values.sort { $0.firstSeenAt > $1.firstSeenAt }
        case .price: values.sort { $0.total < $1.total }
        case .score: values.sort { (model.score(for: $0).percentile ?? 2) < (model.score(for: $1).percentile ?? 2) }
        }
        return values
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 14) {
                if filtered.isEmpty {
                    VintEmptyState(
                        title: favoritesOnly ? "Aucun favori" : "Aucune annonce",
                        message: favoritesOnly ? "Ajoutez une annonce avec le bouton cœur." : "Aucune annonce ne correspond aux filtres.",
                        systemImage: favoritesOnly ? "heart" : "tray"
                    )
                } else {
                    ForEach(filtered) { item in
                        NavigationLink(value: item) {
                            ListingCard(item: item, score: model.score(for: item))
                        }
                        .buttonStyle(.plain)
                        .contextMenu { ListingContextActions(item: item) }
                    }
                }
            }
            .padding()
            .frame(maxWidth: 900)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(title)
        .searchable(text: $query, prompt: "Filtrer les annonces")
        .toolbar {
            Menu {
                Picker("Tri", selection: $sortMode) {
                    ForEach(SortMode.allCases) { Text($0.rawValue).tag($0) }
                }
            } label: {
                Label("Trier", systemImage: "arrow.up.arrow.down")
            }
        }
        .refreshable { await model.refresh() }
        .navigationDestination(for: ListingDTO.self) { ListingDetailView(item: $0) }
    }
}
