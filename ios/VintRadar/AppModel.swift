import Foundation
import Observation
@MainActor @Observable final class AppModel {
    var alerts:[AlertDTO]=[];var listings:[ListingDTO]=[];var dashboard:DashboardDTO?;var loading=false;var error:String?
    let api=APIClient()
    var configured:Bool { UserDefaults.standard.string(forKey:"serverURL") != nil }
    func refresh() async { loading=true;defer{loading=false};do{async let a:[AlertDTO]=api.request("alerts");async let l:[ListingDTO]=api.request("listings");async let d:DashboardDTO=api.request("dashboard");(alerts,listings,dashboard)=try await(a,l,d);error=nil}catch{self.error=String(describing:error)} }
}
