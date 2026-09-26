import XCTest
@testable import VintRadar

final class VintRadarTests: XCTestCase {
    @MainActor
    func testNewListingDTODecodingAndVintedTotal() throws {
        let json = """
        {
          "id":1,"alert_id":1,"alert_ids":[1,2],"external_id":"x","title":"LEGO 42035",
          "description":"Complet","price":30,"total_item_price":32.2,"shipping_estimate":4,
          "buyer_fee":2.2,"currency":"EUR","url":"https://www.vinted.fr/items/x",
          "image_url":null,"image_urls":[],"brand":"LEGO","category_id":"1767",
          "category_name":"Jeux de construction","category_path":["Enfants","Jeux"],
          "colors":["Bleu"],"seller_name":"vendeur","seller_rating":4.9,
          "seller_reviews_count":12,"seller_location":"Paris","seller_created_at":null,
          "seller_last_login_at":null,"condition":"Très bon état","condition_segment":"VERY_GOOD",
          "size":null,"favourite_count":8,"view_count":40,"published_at":null,
          "enrichment_error":null,
          "score_label":"DEAL","score_percentile":0.1,"score_median":52,
          "score_sample_count":17,"score_confidence":"HIGH","pricing_explanation":{},
          "pricing_evaluated":false,"scoring_version":0,
          "status":"ACTIVE","first_seen_at":"2026-09-19T12:00:00Z",
          "updated_at":"2026-09-19T12:00:00Z"
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let listing = try decoder.decode(ListingDTO.self, from: Data(json.utf8))
        XCTAssertEqual(listing.total, 32.2)
        XCTAssertEqual(listing.alertIds, [1, 2])
        XCTAssertEqual(listing.categoryPath, ["Enfants", "Jeux"])
        XCTAssertEqual(listing.pricingEvaluated, false)
        XCTAssertEqual(AppModel().score(for: listing).label, .unknown)
    }

    func testServerScoreIsRepresentable() {
        let score = DealScore(
            label: .deal,
            percentile: 0.1,
            median: 20,
            sampleCount: 12,
            serverConfidence: "MEDIUM"
        )
        XCTAssertEqual(score.label, .deal)
        XCTAssertEqual(score.confidence, "Moyenne")
    }

    func testRobustScoreNeedsComparables() {
        let score = DealScore.calculate(price: 10, comparablePrices: [12, 15])
        XCTAssertEqual(score.label, .unknown)
        XCTAssertNil(score.percentile)
    }

    func testFrenchPricingExplanationAndCorrectionEncoding() throws {
        let explanation = PricingExplanationDTO(
            evaluated: true,
            reason: nil,
            price: PriceBreakdownDTO(item: 30, buyerFee: 2.2, shipping: 0, total: 32.2),
            product: RecognizedProductDTO(key: "lego:42035", model: "42035", confidence: 1, text: "LEGO 42035"),
            conditionSegment: "VERY_GOOD",
            windowDays: 90,
            count: 17,
            median: 52,
            p20: 38,
            p75: 61,
            percentile: 0.12,
            confidence: "HIGH",
            fallbackLevel: 1,
            fallbackLabel: "même produit et même état",
            comparableIds: [2, 3],
            externalReferences: []
        )
        let phrase = PricingPhrase.french(explanation)
        XCTAssertTrue(phrase.contains("17 annonces comparables"))
        XCTAssertTrue(phrase.contains("Confiance élevée"))
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(ProductCorrection(canonicalKey: "lego:42035", excludeFromStats: false))
        XCTAssertTrue(String(decoding: data, as: UTF8.self).contains("canonical_key"))
    }

    func testInterestSignalFromSnapshots() {
        let start = Date(timeIntervalSince1970: 0)
        let snapshots = [
            ListingSnapshotDTO(
                id: 1, listingId: 1, price: 30, totalItemPrice: 32,
                favouriteCount: 2, viewCount: 10, status: "ACTIVE", observedAt: start
            )
        ]
        XCTAssertEqual(
            InterestSignal.text(history: snapshots, currentFavorites: 14, now: start.addingTimeInterval(7200)),
            "+12 favoris en 2 h"
        )
    }

    func testFrenchCurrencyRelativeDateAndUnevaluatedReason() {
        XCTAssertTrue(FrenchFormat.currency(8.05, code: "EUR").contains("8,05"))
        let now = Date(timeIntervalSince1970: 14 * 3600)
        let thirteenHoursAgo = Date(timeIntervalSince1970: 3600)
        let relative = FrenchFormat.relative(thirteenHoursAgo, relativeTo: now).lowercased()
        XCTAssertTrue(relative.contains("13"))
        XCTAssertTrue(relative.contains("heure"))

        let explanation = PricingExplanationDTO(
            evaluated: false,
            reason: "catégorie non déterminée avec confiance",
            price: PriceBreakdownDTO(item: 8, buyerFee: 0.05, shipping: 0, total: 8.05),
            product: RecognizedProductDTO(key: nil, model: nil, confidence: 0, text: nil),
            conditionSegment: nil,
            windowDays: 90,
            count: nil,
            median: nil,
            p20: nil,
            p75: nil,
            percentile: nil,
            confidence: nil,
            fallbackLevel: nil,
            fallbackLabel: nil,
            comparableIds: nil,
            externalReferences: []
        )
        XCTAssertEqual(
            PricingPhrase.french(explanation),
            "Prix non évalué : catégorie non déterminée avec confiance."
        )
    }

    @MainActor
    func testSwiftDataFlagCacheRoundTrip() {
        let store = LocalStore(inMemory: true)
        let flag = FlagDTO(listingId: 42, favorite: true, seen: false, hidden: false)
        store.saveFlags([42: flag])
        XCTAssertEqual(store.loadFlags()[42], flag)
        store.clear()
        XCTAssertTrue(store.loadFlags().isEmpty)
    }
}
