import SwiftUI

@main
struct VintRadarApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(VintTheme.brand)
                .onOpenURL { url in
                    Task { await model.handle(url: url) }
                }
        }
    }
}

