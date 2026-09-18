import SwiftUI

struct OnboardingView: View {
    @Environment(AppModel.self) private var model
    @State private var serverURL = "http://100.64.0.1:8000"
    @State private var token = ""
    @State private var testing = false
    @State private var message: String?
    @FocusState private var focusedField: Field?

    private enum Field { case url, token }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    VStack(alignment: .leading, spacing: 12) {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .font(.system(size: 46, weight: .semibold))
                            .foregroundStyle(VintTheme.accent)
                        Text("Repérez les bonnes affaires avant qu’elles ne disparaissent.")
                            .font(.largeTitle.bold())
                        Text("Connectez l’app à votre serveur VintRadar privé via Tailscale. Votre token reste enregistré sur cet appareil.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }

                    VStack(spacing: 16) {
                        TextField("URL du serveur", text: $serverURL)
                            .textContentType(.URL)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .focused($focusedField, equals: .url)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .token }
                        SecureField("Token API", text: $token)
                            .textContentType(.password)
                            .focused($focusedField, equals: .token)
                            .submitLabel(.done)
                    }
                    .textFieldStyle(.roundedBorder)

                    if let message { ErrorBanner(message: message) }

                    Button {
                        Task { await connect() }
                    } label: {
                        HStack {
                            if testing { ProgressView().tint(.white) }
                            Text(testing ? "Connexion…" : "Tester et continuer")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(testing || token.trimmingCharacters(in: .whitespaces).isEmpty || !serverURL.hasPrefix("http"))

                    Label("VintRadar n’est pas affiliée à Vinted et n’effectue aucun achat automatiquement.", systemImage: "lock.shield")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(24)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Bienvenue")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func connect() async {
        testing = true
        defer { testing = false }
        do {
            let cleanURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
            try await model.api.health(url: cleanURL, token: token)
            model.configure(url: cleanURL, token: token)
            await model.refresh()
        } catch {
            message = error.localizedDescription
        }
    }
}

