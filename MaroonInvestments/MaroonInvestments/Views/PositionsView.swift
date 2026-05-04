import SwiftUI

struct PositionsView: View {
    @State private var positions: [Position] = []
    @State private var isLoading = true
    @State private var closingSymbol: String?
    @State private var toast: String?

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if positions.isEmpty {
                    ContentUnavailableView("No Open Positions", systemImage: "tray")
                } else {
                    List {
                        ForEach(positions) { pos in
                            positionRow(pos)
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Positions")
            .refreshable { await load() }
            .onAppear { Task { await load() } }
            .overlay(alignment: .bottom) {
                if let toast {
                    Text(toast)
                        .font(.subheadline.weight(.medium))
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(.regularMaterial)
                        .clipShape(Capsule())
                        .padding(.bottom, 20)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
        }
    }

    func positionRow(_ pos: Position) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(pos.symbol)
                        .font(.system(size: 16, weight: .bold))
                    Text(pos.side.uppercased())
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(pos.side == "long" ? Color.green.opacity(0.15) : Color.red.opacity(0.15))
                        .foregroundStyle(pos.side == "long" ? .green : .red)
                        .clipShape(Capsule())
                }
                Text("\(pos.qty, specifier: "%.0f") @ \(pos.avg_entry_price, specifier: "$%.2f")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text(pos.current_price, format: .currency(code: "USD"))
                    .font(.system(size: 15, weight: .semibold))
                HStack(spacing: 4) {
                    Text(pos.unrealized_pl, format: .currency(code: "USD"))
                    Text("(\(pos.unrealized_plpc * 100, specifier: "%.2f")%)")
                }
                .font(.caption)
                .foregroundStyle(pos.unrealized_pl >= 0 ? .green : .red)
            }
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button(role: .destructive) {
                Task { await closePosition(pos.symbol) }
            } label: {
                Label("Close", systemImage: "xmark.circle.fill")
            }
            .tint(maroon)
        }
    }

    func closePosition(_ symbol: String) async {
        do {
            try await APIService.shared.delete("/api/positions/\(symbol)")
            await MainActor.run {
                positions.removeAll { $0.symbol == symbol }
                showToast("Closed \(symbol)")
            }
        } catch {
            await MainActor.run { showToast("Failed to close \(symbol)") }
        }
    }

    func showToast(_ msg: String) {
        withAnimation { toast = msg }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation { toast = nil }
        }
    }

    func load() async {
        do {
            let resp = try await APIService.shared.fetch("/api/account", as: AccountResponse.self)
            await MainActor.run {
                positions = resp.positions ?? []
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
