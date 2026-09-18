import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Group {
            if model.isConfigured { MainTabs() } else { OnboardingView() }
        }
        .animation(.snappy, value: model.isConfigured)
    }
}

private enum AppTab: Hashable {
    case home, alerts, favorites, settings
}

struct MainTabs: View {
    @Environment(AppModel.self) private var model
    @State private var selection: AppTab = .home

    var body: some View {
        @Bindable var model = model
        TabView(selection: $selection) {
            Tab("Accueil", systemImage: "house", value: .home) { HomeView() }
            Tab("Alertes", systemImage: "dot.radiowaves.left.and.right", value: .alerts) { AlertsView() }
            Tab("Favoris", systemImage: "heart", value: .favorites) { FavoritesView() }
            Tab("Réglages", systemImage: "gearshape", value: .settings) { SettingsView() }
        }
        .sheet(item: $model.deepLinkTarget) { target in
            NavigationStack {
                switch target {
                case .listing(let item): ListingDetailView(item: item)
                case .alert(let alert): ListingsView(title: alert.name, alertID: alert.id)
                }
            }
        }
    }
}

