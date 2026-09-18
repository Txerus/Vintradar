import SwiftUI
struct AlertsView:View {
    @Environment(AppModel.self) private var model
    var body:some View { NavigationStack { List(model.alerts){a in NavigationLink{ListingsView(title:a.name,alertID:a.id)}label:{VStack(alignment:.leading){Text(a.name).font(.headline);Text(a.paused ? "En pause" : "Scan toutes les \(a.scanMinutes) min").font(.caption).foregroundStyle(.secondary)}}}.navigationTitle("Alertes").toolbar{Button("",systemImage:"plus"){}}.refreshable{await model.refresh()}.task{if model.alerts.isEmpty{await model.refresh()}} } }
}
