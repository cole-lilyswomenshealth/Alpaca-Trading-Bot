import SwiftUI

struct PortfolioView: View {
    @State private var account: AccountData?
    @State private var positions: [Position] = []
    @State private var isLoading = true
    @State private var error: String?

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)
    let timer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if let account {
                        // Stats card
                        statsCard(account: account)
                    } else if isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity, minHeight: 120)
                    }

                    // Positions preview
                    if !positions.isEmpty {
                        positionsCard
                    }
                }
                .padding()
            }
            .navigationTitle("Portfolio")
            .navigationBarTitleDisplayMode(.large)
            .background(Color(.systemGroupedBackground))
            .refreshable { await load() }
            .onAppear { Task { await load() } }
            .onReceive(timer) { _ in Task { await load() } }
        }
    }

    func statsCard(account: AccountData) -> some View {
        VStack(spacing: 0) {
            // Equity
            VStack(spacing: 4) {
                Text(account.equityDouble, format: .currency(code: "USD"))
                    .font(.system(size: 36, weight: .bold, design: .rounded))
                    .foregroundStyle(.primary)
                Text("Portfolio Value")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 20)

            Divider()

            // Row of stats
            HStack(spacing: 0) {
                statCell(
                    label: "Day P&L",
                    value: account.dayPL,
                    isCurrency: true,
                    showSign: true
                )
                Divider().frame(height: 44)
                statCell(
                    label: "Buying Power",
                    value: account.buyingPowerDouble,
                    isCurrency: true,
                    showSign: false
                )
                Divider().frame(height: 44)
                statCell(
                    label: "Positions",
                    value: Double(positions.count),
                    isCurrency: false,
                    showSign: false
                )
            }
            .padding(.vertical, 8)
        }
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(maroon.opacity(0.3), lineWidth: 1)
        )
    }

    func statCell(label: String, value: Double, isCurrency: Bool, showSign: Bool) -> some View {
        VStack(spacing: 4) {
            Group {
                if isCurrency {
                    Text(value, format: .currency(code: "USD"))
                } else {
                    Text(String(Int(value)))
                }
            }
            .font(.system(size: 15, weight: .semibold, design: .rounded))
            .foregroundStyle(
                showSign ? (value >= 0 ? .green : .red) : .primary
            )
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    var positionsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Open Positions")
                .font(.headline)
                .padding(.horizontal)
                .padding(.top, 12)

            ForEach(positions) { pos in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(pos.symbol)
                            .font(.system(size: 14, weight: .semibold))
                        Text("\(pos.qty, specifier: "%.0f") shares · \(pos.side.capitalized)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(pos.current_price, format: .currency(code: "USD"))
                            .font(.system(size: 14, weight: .medium))
                        Text(pos.unrealized_pl, format: .currency(code: "USD"))
                            .font(.caption)
                            .foregroundStyle(pos.unrealized_pl >= 0 ? .green : .red)
                    }
                }
                .padding(.horizontal)

                if pos.id != positions.last?.id {
                    Divider().padding(.leading)
                }
            }
            .padding(.bottom, 12)
        }
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(maroon.opacity(0.2), lineWidth: 1)
        )
    }

    func load() async {
        do {
            let resp = try await APIService.shared.fetch("/api/account", as: AccountResponse.self)
            await MainActor.run {
                account = resp.account
                positions = resp.positions ?? []
                isLoading = false
            }
        } catch {
            await MainActor.run {
                self.error = error.localizedDescription
                isLoading = false
            }
        }
    }
}
