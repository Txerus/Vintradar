import SwiftUI
struct HomeView:View {
    @Environment(AppModel.self) private var model
    var body:some View { NavigationStack { ScrollView { VStack(alignment:.leading,spacing:20){if let d=model.dashboard{HStack{StatCard(value:"\(d.active)",label:"actives");StatCard(value:"\(d.listings)",label:"analysées")}};Text("Meilleures annonces").font(.title2.bold());ForEach(model.listings.prefix(8)){ListingCard(item:$0)}}.padding()} .navigationTitle("VintRadar").refreshable{await model.refresh()}.task{await model.refresh()} } }
}
struct StatCard:View{let value:String;let label:String;var body:some View{VStack(alignment:.leading){Text(value).font(.largeTitle.bold());Text(label).foregroundStyle(.secondary)}.frame(maxWidth:.infinity,alignment:.leading).padding().glassEffect(.regular,in:RoundedRectangle(cornerRadius:24))}}
