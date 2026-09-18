import SwiftUI

struct StatCard: View {
    let value: String
    let label: String
    let systemImage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: systemImage)
                .font(.title3.weight(.semibold))
                .foregroundStyle(VintTheme.brand)
            Text(value).font(.title.bold()).contentTransition(.numericText())
            Text(label).font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 22))
        .accessibilityElement(children: .combine)
    }
}

struct ScoreBadge: View {
    let score: DealScore

    var body: some View {
        Label(score.label.title, systemImage: score.label.symbol)
            .font(.caption.weight(.bold))
            .foregroundStyle(score.label.color)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(score.label.color.opacity(0.13), in: Capsule())
            .accessibilityLabel("Score : \(score.label.title)")
    }
}

struct ServerStatusChip: View {
    let isOnline: Bool
    let lastScan: Date?

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(isOnline ? VintTheme.deal : VintTheme.danger).frame(width: 9, height: 9)
            Text(isOnline ? "Serveur connecté" : "Données hors ligne")
            if let lastScan { Text("· \(lastScan.formatted(.relative(presentation: .named)))") }
        }
        .font(.caption.weight(.medium))
        .foregroundStyle(.secondary)
        .accessibilityElement(children: .combine)
    }
}

struct VintEmptyState: View {
    let title: String
    let message: String
    let systemImage: String

    var body: some View {
        ContentUnavailableView(title, systemImage: systemImage, description: Text(message))
    }
}

struct ErrorBanner: View {
    let message: String
    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(.footnote)
            .foregroundStyle(VintTheme.danger)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(VintTheme.danger.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
            .accessibilityLabel("Erreur : \(message)")
    }
}

