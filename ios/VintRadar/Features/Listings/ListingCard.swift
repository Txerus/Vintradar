import SwiftUI

struct ListingCard: View {
    @Environment(AppModel.self) private var model
    let item: ListingDTO
    let score: DealScore

    var body: some View {
        HStack(spacing: 14) {
            AsyncImage(url: item.imageUrl.flatMap(URL.init)) { phase in
                switch phase {
                case .success(let image): image.resizable().scaledToFill()
                case .failure: Image(systemName: "photo").font(.title).foregroundStyle(.secondary)
                default: ProgressView()
                }
            }
            .frame(width: 108, height: 108)
            .background(.quaternary)
            .clipShape(RoundedRectangle(cornerRadius: 18))

            VStack(alignment: .leading, spacing: 7) {
                HStack(alignment: .top) {
                    Text(item.title).font(.headline).lineLimit(2)
                    Spacer(minLength: 4)
                    if model.flags[item.id]?.favorite == true {
                        Image(systemName: "heart.fill").foregroundStyle(.red).accessibilityLabel("Favori")
                    }
                }
                Text(FrenchFormat.currency(item.total, code: item.currency)).font(.title3.bold())
                HStack {
                    Text(item.condition ?? "État non précisé")
                    Text("·")
                    Text(FrenchFormat.relative(item.firstSeenAt))
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                if score.label != .unknown {
                    ScoreBadge(score: score)
                }
                Text(shortReason)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .opacity(model.flags[item.id]?.seen == true ? 0.78 : 1)
        .glassEffect(.regular, in: .rect(cornerRadius: 24))
        .accessibilityElement(children: .combine)
        .accessibilityHint("Ouvre le détail de l’annonce")
    }

    private var shortReason: String {
        guard let median = item.scoreMedian, let count = item.scoreSampleCount, count > 0 else {
            return "Prix non évalué"
        }
        let difference = Int(((item.total / median - 1) * 100).rounded())
        return "\(difference > 0 ? "+" : "")\(difference) % vs \(count) comparables"
    }
}

struct ListingContextActions: View {
    @Environment(AppModel.self) private var model
    let item: ListingDTO

    var body: some View {
        Button {
            Task { await model.setFavorite(item) }
        } label: {
            Label(model.flags[item.id]?.favorite == true ? "Retirer des favoris" : "Ajouter aux favoris", systemImage: model.flags[item.id]?.favorite == true ? "heart.slash" : "heart")
        }
        Button(role: .destructive) {
            Task { await model.setHidden(item) }
        } label: {
            Label("Masquer", systemImage: "eye.slash")
        }
    }
}
