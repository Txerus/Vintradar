import Foundation

enum FrenchFormat {
    static let locale = Locale(identifier: "fr_FR")

    static func currency(_ value: Double, code: String) -> String {
        value.formatted(.currency(code: code).locale(locale))
    }

    static func relative(_ date: Date, relativeTo reference: Date = Date()) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = locale
        formatter.unitsStyle = .full
        return formatter.localizedString(for: date, relativeTo: reference)
    }

    static func dateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    static func monthYear(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.setLocalizedDateFormatFromTemplate("MMMM yyyy")
        return formatter.string(from: date)
    }
}

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
        return "Prix situé au percentile \(Int((percentile * 100).rounded())) sur \(sampleCount) annonces comparables. Médiane : \(FrenchFormat.currency(median, code: "EUR")). Confiance \(confidence.lowercased())."
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

enum PricingPhrase {
    static func french(_ explanation: PricingExplanationDTO, currency: String = "EUR") -> String {
        guard explanation.evaluated,
              let median = explanation.median,
              let percentile = explanation.percentile,
              let count = explanation.count else {
            return "Prix non évalué : \(explanation.reason ?? "pas assez d’annonces comparables")."
        }
        let total = FrenchFormat.currency(explanation.price.total, code: currency)
        let item = FrenchFormat.currency(explanation.price.item, code: currency)
        let fee = FrenchFormat.currency(explanation.price.buyerFee, code: currency)
        let medianText = FrenchFormat.currency(median, code: currency)
        let below = Int(abs((explanation.price.total / median - 1) * 100).rounded())
        let direction = explanation.price.total <= median ? "sous" : "au-dessus de"
        let confidence: String
        switch explanation.confidence {
        case "HIGH": confidence = "élevée"
        case "MEDIUM": confidence = "moyenne"
        default: confidence = "faible"
        }
        let fallback = explanation.fallbackLabel.map { " Niveau de comparaison : \($0)." } ?? ""
        return "\(item) + \(fee) de protection acheteur = \(total). C’est \(below) % \(direction) la médiane de \(medianText), calculée sur \(count) annonces comparables vues ces \(explanation.windowDays) derniers jours (percentile \(Int((percentile * 100).rounded()))). Confiance \(confidence).\(fallback)"
    }

    static func short(_ explanation: PricingExplanationDTO) -> String {
        guard explanation.evaluated, let median = explanation.median, let count = explanation.count else {
            return "Prix non évalué"
        }
        let difference = Int(((explanation.price.total / median - 1) * 100).rounded())
        return "\(difference > 0 ? "+" : "")\(difference) % vs \(count) comparables"
    }
}
