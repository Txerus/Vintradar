import SwiftUI
import Charts
struct ListingDetailView: View {
    let item: ListingDTO
    private var comparisonPrices: [Double] { [item.total * 0.8, item.total * 0.9, item.total, item.total * 1.1, item.total * 1.2] }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                AsyncImage(url: item.imageUrl.flatMap(URL.init)) { image in image.resizable().scaledToFit() } placeholder: { Rectangle().fill(.quaternary).frame(height: 320) }
                VStack(alignment: .leading, spacing: 12) {
                    Text(item.title).font(.title.bold())
                    Text(item.total, format: .currency(code: item.currency)).font(.largeTitle.bold())
                    Text(item.condition ?? "État non précisé").foregroundStyle(.secondary)
                    Chart(comparisonPrices, id: \.self) { value in BarMark(x: .value("Prix", value), y: .value("Comparables", 1)) }.frame(height: 130)
                    if !item.description.isEmpty { Text(item.description) }
                    if let url = URL(string: item.url) { Link("Voir sur Vinted", destination: url).buttonStyle(.borderedProminent).controlSize(.large).frame(maxWidth: .infinity) }
                }.padding()
            }
        }.navigationBarTitleDisplayMode(.inline)
    }
}
