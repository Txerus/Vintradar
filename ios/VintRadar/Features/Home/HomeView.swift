import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var model
    @State private var query = ""

    private var searchResults: [ListingDTO] {
        guard !query.isEmpty else { return Array(bestDeals.prefix(8)) }
        return model.visibleListings.filter {
            $0.title.localizedCaseInsensitiveContains(query) ||
            $0.description.localizedCaseInsensitiveContains(query) ||
            ($0.condition?.localizedCaseInsensitiveContains(query) ?? false)
        }
    }

    private var bestDeals: [ListingDTO] {
        model.visibleListings.sorted {
            let lhs = model.score(for: $0).percentile ?? 2
            let rhs = model.score(for: $1).percentile ?? 2
            return lhs == rhs ? $0.firstSeenAt > $1.firstSeenAt : lhs < rhs
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    ServerStatusChip(isOnline: model.isOnline, lastScan: model.dashboard?.lastScanAt)
                    if let status = model.workerStatus {
                        HStack {
                            Label("File : \(status.enrichmentQueueSize ?? 0)", systemImage: "tray.full")
                            Spacer()
                            Text("403 : \(status.recent403Count ?? 0) · 429 : \(status.recent429Count ?? 0)")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        if let error = status.lastError {
                            ErrorBanner(message: "Worker : \(error)")
                        }
                    }

                    if let error = model.errorMessage { ErrorBanner(message: error) }

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        StatCard(value: "\(model.dashboard?.active ?? 0)", label: "annonces actives", systemImage: "bolt.fill")
                        StatCard(value: "\(model.dashboard?.listings ?? model.listings.count)", label: "annonces analysées", systemImage: "chart.bar.xaxis")
                        StatCard(value: "\(model.dashboard?.alerts ?? model.alerts.count)", label: "alertes suivies", systemImage: "bell.badge")
                        StatCard(value: "\(model.favoriteListings.count)", label: "favoris", systemImage: "heart.fill")
                    }

                    HStack {
                        Text(query.isEmpty ? "Meilleures affaires" : "Résultats")
                            .font(.title2.bold())
                        Spacer()
                        if model.loading { ProgressView() }
                    }

                    if searchResults.isEmpty {
                        VintEmptyState(
                            title: query.isEmpty ? "Aucune annonce" : "Aucun résultat",
                            message: query.isEmpty ? "Les nouvelles annonces apparaîtront après le prochain scan." : "Essayez avec un autre mot-clé.",
                            systemImage: "magnifyingglass"
                        )
                    } else {
                        ForEach(searchResults) { item in
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
            .navigationTitle("VintRadar")
            .searchable(text: $query, prompt: "Rechercher une annonce")
            .refreshable { await model.refresh() }
            .navigationDestination(for: ListingDTO.self) { ListingDetailView(item: $0) }
            .task { if !model.loading { await model.refresh() } }
        }
    }
}
