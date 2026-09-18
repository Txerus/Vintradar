import XCTest
@testable import VintRadar
final class VintRadarTests:XCTestCase { func testTotal(){let d=Date();let x=ListingDTO(id:1,alertId:1,externalId:"x",title:"x",description:"",price:10,shippingEstimate:2,buyerFee:1,currency:"EUR",url:"https://example.com",imageUrl:nil,condition:nil,size:nil,status:"ACTIVE",createdAt:d,updatedAt:d);XCTAssertEqual(x.total,13)} }
