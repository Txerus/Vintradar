import SwiftUI
struct ListingsView: View {
    let title: String
    var alertID: Int? = nil
    @Environment(AppModel.self) private var model
    var filtered: [ListingDTO] { alertID == nil ? model.listings : model.listings.filter { $0.alertId == alertID } }
    var body: some View {
        ScrollView { LazyVStack(spacing: 14) { ForEach(filtered) { item in NavigationLink { ListingDetailView(item: item) } label: { ListingCard(item: item) }.buttonStyle(.plain) } }.padding() }.navigationTitle(title)
    }
}
struct ListingCard: View {
    let item: ListingDTO
    var body: some View {
        HStack(spacing: 14) {
            AsyncImage(url: item.imageUrl.flatMap(URL.init)) { image in image.resizable().scaledToFill() } placeholder: { Rectangle().fill(.quaternary) }
                .frame(width: 104, height: 104).clipShape(RoundedRectangle(cornerRadius: 18))
            VStack(alignment: .leading, spacing: 8) {
                Text(item.title).font(.headline).lineLimit(2)
                Text(item.total, format: .currency(code: item.currency)).font(.title3.bold())
                Text(item.condition ?? "État non précisé").font(.caption).foregroundStyle(.secondary)
                Text("NOUVEAU").font(.caption2.bold()).padding(.horizontal, 8).padding(.vertical, 4).background(.indigo.opacity(0.15), in: Capsule())
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.padding(10).glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24)).accessibilityElement(children: .combine)
    }
}
