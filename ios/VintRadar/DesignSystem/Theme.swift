import SwiftUI

enum VintTheme {
    static let brand = Color(red: 0.12, green: 0.23, blue: 0.54)
    static let accent = Color(red: 0.95, green: 0.57, blue: 0.16)
    static let deal = Color(red: 0.08, green: 0.55, blue: 0.38)
    static let warning = Color(red: 0.76, green: 0.40, blue: 0.05)
    static let danger = Color(red: 0.78, green: 0.12, blue: 0.18)
}

extension DealLabel {
    var color: Color {
        switch self {
        case .deal: VintTheme.deal
        case .good: .blue
        case .normal: .secondary
        case .expensive: VintTheme.warning
        case .unknown: .secondary
        }
    }

    var symbol: String {
        switch self {
        case .deal: "bolt.fill"
        case .good: "checkmark.seal.fill"
        case .normal: "equal.circle.fill"
        case .expensive: "exclamationmark.triangle.fill"
        case .unknown: "questionmark.circle.fill"
        }
    }
}

