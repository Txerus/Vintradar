import SwiftUI
@main struct VintRadarApp:App {
    @State private var model=AppModel()
    var body:some Scene { WindowGroup { RootView().environment(model).tint(.indigo).onOpenURL{url in NotificationCenter.default.post(name:.deepLink,object:url)} } }
}
extension Notification.Name { static let deepLink=Notification.Name("VintRadarDeepLink") }
