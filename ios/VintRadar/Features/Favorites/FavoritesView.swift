import SwiftUI

struct FavoritesView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            ListingsView(title: "Favoris", favoritesOnly: true)
                .toolbar {
                    if !model.favoriteListings.isEmpty {
                        Text("\(model.favoriteListings.count)").foregroundStyle(.secondary)
                    }
                }
        }
    }
}

