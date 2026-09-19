import Foundation

enum DealLabel: String, CaseIterable, Codable, Sendable {
    case deal = "DEAL"
    case good = "GOOD"
    case normal = "NORMAL"
    case expensive = "EXPENSIVE"
    case unknown = "UNKNOWN"

    var title: String {
        switch self {
        case .deal: "Excellente affaire"
        case .good: "Bon prix"
        case .normal: "Prix normal"
        case .expensive: "Prix élevé"
        case .unknown: "À qualifier"
        }
    }
}

struct DealScore: Hashable, Sendable {
    let label: DealLabel
    let percentile: Double?
    let median: Double?
    let sampleCount: Int
    var serverConfidence: String? = nil

    var confidence: String {
        if let serverConfidence {
            switch serverConfidence {
            case "HIGH": return "Élevée"
            case "MEDIUM": return "Moyenne"
            case "LOW": return "Faible"
            default: break
            }
        }
        if sampleCount >= 30 { return "Élevée" }
        if sampleCount >= 10 { return "Moyenne" }
        return "Faible"
    }

    var explanation: String {
        guard let percentile, let median else {
            return "Pas assez d’annonces comparables pour calculer un score fiable."
        }
        return "Prix situé au percentile \(Int((percentile * 100).rounded())) sur \(sampleCount) annonces comparables. Médiane : \(median.formatted(.currency(code: "EUR"))). Confiance \(confidence.lowercased())."
    }

    static func calculate(price: Double, comparablePrices: [Double]) -> DealScore {
        let sorted = comparablePrices.filter { $0 > 0 }.sorted()
        guard sorted.count >= 3 else {
            return DealScore(label: .unknown, percentile: nil, median: nil, sampleCount: sorted.count)
        }
        let percentile = Double(sorted.filter { $0 <= price }.count) / Double(sorted.count)
        let median: Double
        if sorted.count.isMultiple(of: 2) {
            median = (sorted[sorted.count / 2 - 1] + sorted[sorted.count / 2]) / 2
        } else {
            median = sorted[sorted.count / 2]
        }
        let label: DealLabel = percentile <= 0.20 ? .deal : percentile < 0.50 ? .good : percentile <= 0.75 ? .normal : .expensive
        return DealScore(label: label, percentile: percentile, median: median, sampleCount: sorted.count)
    }
}
