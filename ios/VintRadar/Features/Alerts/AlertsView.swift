import SwiftUI

struct AlertsView: View {
    @Environment(AppModel.self) private var model
    @State private var editorMode: AlertEditorMode?
    @State private var alertToDelete: AlertDTO?

    var body: some View {
        NavigationStack {
            List {
                if let error = model.errorMessage { ErrorBanner(message: error).listRowSeparator(.hidden) }
                if model.alerts.isEmpty {
                    VintEmptyState(
                        title: "Aucune alerte",
                        message: "Créez votre première veille pour commencer à détecter des annonces.",
                        systemImage: "bell.badge"
                    )
                    .listRowSeparator(.hidden)
                } else {
                    ForEach(model.alerts) { alert in
                        NavigationLink(value: alert) {
                            AlertRow(alert: alert)
                        }
                        .swipeActions(edge: .leading) {
                            Button {
                                Task { await model.togglePause(alert) }
                            } label: {
                                Label(alert.paused ? "Reprendre" : "Pause", systemImage: alert.paused ? "play.fill" : "pause.fill")
                            }
                            .tint(alert.paused ? VintTheme.deal : VintTheme.warning)
                        }
                        .swipeActions(edge: .trailing) {
                            Button { editorMode = .edit(alert) } label: { Label("Modifier", systemImage: "pencil") }.tint(VintTheme.brand)
                            Button(role: .destructive) { alertToDelete = alert } label: { Label("Supprimer", systemImage: "trash") }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Alertes")
            .toolbar {
                Button { editorMode = .create } label: { Label("Nouvelle alerte", systemImage: "plus") }
            }
            .navigationDestination(for: AlertDTO.self) { alert in
                ListingsView(title: alert.name, alertID: alert.id)
                    .toolbar {
                        Button("Modifier") { editorMode = .edit(alert) }
                    }
            }
            .sheet(item: $editorMode) { mode in AlertEditorView(mode: mode) }
            .confirmationDialog("Supprimer cette alerte ?", isPresented: Binding(
                get: { alertToDelete != nil },
                set: { if !$0 { alertToDelete = nil } }
            ), titleVisibility: .visible) {
                Button("Supprimer", role: .destructive) {
                    guard let alertToDelete else { return }
                    Task { await model.deleteAlert(alertToDelete) }
                }
                Button("Annuler", role: .cancel) {}
            } message: {
                Text("Les annonces associées seront également retirées du serveur.")
            }
            .refreshable { await model.refresh() }
            .task { if model.alerts.isEmpty { await model.refresh() } }
        }
    }
}

private struct AlertRow: View {
    let alert: AlertDTO

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: alert.paused ? "pause.circle.fill" : "dot.radiowaves.left.and.right")
                .font(.title2)
                .foregroundStyle(alert.paused ? .secondary : VintTheme.brand)
                .frame(width: 38, height: 38)
                .background(.quaternary, in: Circle())
            VStack(alignment: .leading, spacing: 5) {
                Text(alert.name).font(.headline)
                Text(alert.includeTerms.isEmpty ? "Tous les termes" : alert.includeTerms.joined(separator: ", "))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                HStack {
                    Text(alert.paused ? "En pause" : "Toutes les \(alert.scanMinutes) min")
                    if let lastScanAt = alert.lastScanAt { Text("· \(lastScanAt.formatted(.relative(presentation: .named)))") }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
    }
}

