import SwiftUI
struct RootView:View {
    @Environment(AppModel.self) private var model
    var body:some View { Group { if model.configured { MainTabs() } else { OnboardingView() } } }
}
struct MainTabs:View {
    var body:some View { TabView { Tab("Accueil",systemImage:"house"){HomeView()};Tab("Alertes",systemImage:"dot.radiowaves.left.and.right"){AlertsView()};Tab("Favoris",systemImage:"heart"){ListingsView(title:"Favoris")};Tab("Réglages",systemImage:"gearshape"){SettingsView()} } }
}
