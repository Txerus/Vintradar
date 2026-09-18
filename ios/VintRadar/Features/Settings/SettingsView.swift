import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
    @State private var token = UserDefaults.standard.string(forKey: "apiToken") ?? ""
    @State private var testing = false
    @State private var statusMessage: String?
    @State private var showDisconnectConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section("État du service") {
                    LabeledContent("API", value: model.isOnline ? "Connectée" : "Hors ligne")
                    if let lastScan = model.workerStatus?.lastScanAt {
                        LabeledContent("Dernier scan", value: lastScan.formatted(date: .abbreviated, time: .shortened))
                    }
                    LabeledContent("Cache local", value: "\(model.listings.count) annonces")
                }

                Section("Serveur privé") {
                    TextField("URL Tailscale", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField("Token API", text: $token)
                    Button(testing ? "Test en cours…" : "Tester et enregistrer") {
                        Task { await testAndSave() }
                    }
                    .disabled(testing || serverURL.isEmpty || token.isEmpty)
                    if let statusMessage { Text(statusMessage).font(.footnote).foregroundStyle(.secondary) }
                }

                Section("Notifications") {
                    Label("Les notifications temps réel sont envoyées par ntfy.", systemImage: "bell.badge")
                    Text("Installez ntfy sur cet appareil et abonnez-vous au topic configuré sur le serveur.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("À propos") {
                    LabeledContent("Version", value: "0.1.0")
                    LabeledContent("Compatibilité", value: "iOS 26 et versions ultérieures")
                    Text("VintRadar est une application personnelle non affiliée à Vinted. Elle n’automatise ni achat, ni message, ni action sur un compte.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section {
                    Button("Déconnecter ce serveur", role: .destructive) { showDisconnectConfirmation = true }
                }
            }
            .navigationTitle("Réglages")
            .confirmationDialog("Déconnecter VintRadar ?", isPresented: $showDisconnectConfirmation, titleVisibility: .visible) {
                Button("Déconnecter et vider le cache", role: .destructive) { model.disconnect() }
                Button("Annuler", role: .cancel) {}
            }
        }
    }

    private func testAndSave() async {
        testing = true
        defer { testing = false }
        do {
            try await model.api.health(url: serverURL, token: token)
            model.configure(url: serverURL, token: token)
            statusMessage = "Connexion réussie et configuration enregistrée."
            await model.refresh()
        } catch {
            statusMessage = "Échec : \(error.localizedDescription)"
        }
    }
}

