import SwiftUI

enum AlertEditorMode: Identifiable {
    case create
    case edit(AlertDTO)

    var id: String {
        switch self {
        case .create: "create"
        case .edit(let alert): "edit-\(alert.id)"
        }
    }

    var alert: AlertDTO? {
        if case .edit(let alert) = self { return alert }
        return nil
    }
}

struct AlertEditorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: AlertEditorMode

    @State private var name: String
    @State private var includeTerms: String
    @State private var excludeTerms: String
    @State private var minimumPrice: String
    @State private var maximumPrice: String
    @State private var scanMinutes: Int
    @State private var threshold: String
    @State private var saving = false

    init(mode: AlertEditorMode) {
        self.mode = mode
        let draft = mode.alert.map(AlertDraft.init(alert:)) ?? AlertDraft()
        _name = State(initialValue: draft.name)
        _includeTerms = State(initialValue: draft.includeTerms.joined(separator: ", "))
        _excludeTerms = State(initialValue: draft.excludeTerms.joined(separator: ", "))
        _minimumPrice = State(initialValue: draft.minPrice.map { String($0) } ?? "")
        _maximumPrice = State(initialValue: draft.maxPrice.map { String($0) } ?? "")
        _scanMinutes = State(initialValue: draft.scanMinutes)
        _threshold = State(initialValue: draft.notifyThreshold)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Recherche") {
                    TextField("Nom de l’alerte", text: $name)
                    TextField("Termes inclus, séparés par des virgules", text: $includeTerms)
                        .textInputAutocapitalization(.never)
                    TextField("Termes exclus, séparés par des virgules", text: $excludeTerms)
                        .textInputAutocapitalization(.never)
                }
                Section("Budget") {
                    TextField("Prix minimum", text: $minimumPrice).keyboardType(.decimalPad)
                    TextField("Prix maximum", text: $maximumPrice).keyboardType(.decimalPad)
                }
                Section("Surveillance") {
                    Picker("Fréquence", selection: $scanMinutes) {
                        ForEach([5, 10, 15, 30, 60], id: \.self) { Text("\($0) min").tag($0) }
                    }
                    Picker("Notifier à partir de", selection: $threshold) {
                        Text("Excellente affaire").tag("DEAL")
                        Text("Bon prix").tag("GOOD")
                        Text("Toutes").tag("NORMAL")
                    }
                }
                Section {
                    Text("Le serveur respecte une cadence globale prudente. Une fréquence courte ne garantit pas un scan à la seconde près.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle(mode.alert == nil ? "Nouvelle alerte" : "Modifier l’alerte")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Annuler") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Enregistrement…" : "Enregistrer") { Task { await save() } }
                        .disabled(saving || name.trimmingCharacters(in: .whitespaces).isEmpty || includeTermsList.isEmpty)
                }
            }
        }
    }

    private var includeTermsList: [String] { parseTerms(includeTerms) }
    private func parseTerms(_ value: String) -> [String] {
        value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var draft = AlertDraft()
        draft.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        draft.includeTerms = includeTermsList
        draft.excludeTerms = parseTerms(excludeTerms)
        draft.minPrice = Double(minimumPrice.replacingOccurrences(of: ",", with: "."))
        draft.maxPrice = Double(maximumPrice.replacingOccurrences(of: ",", with: "."))
        draft.scanMinutes = scanMinutes
        draft.notifyThreshold = threshold
        draft.paused = mode.alert?.paused ?? false
        if await model.saveAlert(draft, editing: mode.alert) { dismiss() }
    }
}
