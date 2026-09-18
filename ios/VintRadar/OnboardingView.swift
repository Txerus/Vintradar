import SwiftUI
struct OnboardingView:View {
    @Environment(AppModel.self) private var model
    @State private var url="http://100.64.0.1:8000";@State private var token="";@State private var testing=false;@State private var message=""
    var body:some View { NavigationStack { Form { Section("Serveur VintRadar"){TextField("URL Tailscale",text:$url).textInputAutocapitalization(.never).keyboardType(.URL);SecureField("Token API",text:$token)};Section{Button(testing ? "Test…" : "Tester et enregistrer"){Task{testing=true;defer{testing=false};do{try await model.api.health(url:url,token:token);UserDefaults.standard.set(url,forKey:"serverURL");UserDefaults.standard.set(token,forKey:"apiToken");message="Connexion réussie"}catch{message="Échec : \(error)"}}}.disabled(testing || token.isEmpty);if !message.isEmpty{Text(message)}} } .navigationTitle("Bienvenue") } }
}
