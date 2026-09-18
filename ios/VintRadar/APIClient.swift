import Foundation
actor APIClient {
    enum Error: Swift.Error { case notConfigured, badResponse(Int) }
    private let decoder:JSONDecoder={let d=JSONDecoder();d.keyDecodingStrategy = .convertFromSnakeCase;d.dateDecodingStrategy = .iso8601;return d}()
    func request<T:Decodable & Sendable>(_ path:String, as:T.Type=T.self) async throws -> T {
        guard let raw=UserDefaults.standard.string(forKey:"serverURL"),let base=URL(string:raw),let token=UserDefaults.standard.string(forKey:"apiToken") else { throw Error.notConfigured }
        var req=URLRequest(url:base.appending(path:path));req.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
        let (data,response)=try await URLSession.shared.data(for:req);let code=(response as? HTTPURLResponse)?.statusCode ?? 0;guard 200..<300 ~= code else {throw Error.badResponse(code)};return try decoder.decode(T.self,from:data)
    }
    func health(url:String,token:String) async throws { guard let base=URL(string:url) else {throw Error.notConfigured};var req=URLRequest(url:base.appending(path:"health"));req.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization");let (_,r)=try await URLSession.shared.data(for:req);guard (r as? HTTPURLResponse)?.statusCode==200 else{throw Error.badResponse((r as? HTTPURLResponse)?.statusCode ?? 0)} }
}
