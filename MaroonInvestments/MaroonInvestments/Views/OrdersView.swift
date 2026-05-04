import SwiftUI

struct OrdersView: View {
    @State private var orders: [Order] = []
    @State private var isLoading = true
    @State private var toast: String?

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if orders.isEmpty {
                    ContentUnavailableView("No Orders", systemImage: "list.clipboard")
                } else {
                    List(orders) { order in
                        orderRow(order)
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Orders")
            .refreshable { await load() }
            .onAppear { Task { await load() } }
            .overlay(alignment: .bottom) {
                if let toast {
                    Text(toast)
                        .font(.subheadline.weight(.medium))
                        .padding(.horizontal, 20).padding(.vertical, 12)
                        .background(.regularMaterial).clipShape(Capsule())
                        .padding(.bottom, 20)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
        }
    }

    func orderRow(_ order: Order) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(order.symbol)
                        .font(.system(size: 15, weight: .bold))
                    statusBadge(order.status)
                }
                Text("\(order.side.uppercased()) · \(order.type.uppercased()) · \(order.filled_qty ?? order.qty, specifier: "%.0f") shares")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let time = order.submitted_at {
                    Text(formatDate(time))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                if let price = order.filled_avg_price {
                    Text(price, format: .currency(code: "USD"))
                        .font(.system(size: 14, weight: .semibold))
                } else if let lp = order.limit_price {
                    Text("Limit \(lp, format: .currency(code: "USD"))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            if ["new", "accepted", "pending_new"].contains(order.status) {
                Button(role: .destructive) {
                    Task { await cancelOrder(order.id) }
                } label: {
                    Label("Cancel", systemImage: "xmark")
                }
                .tint(maroon)
            }
        }
    }

    @ViewBuilder
    func statusBadge(_ status: String) -> some View {
        let (color, bg): (Color, Color) = {
            switch status {
            case "filled": return (.green, .green.opacity(0.12))
            case "canceled": return (.red, .red.opacity(0.12))
            default: return (.orange, .orange.opacity(0.12))
            }
        }()
        Text(status)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(bg).foregroundStyle(color)
            .clipShape(Capsule())
    }

    func cancelOrder(_ id: String) async {
        do {
            try await APIService.shared.delete("/api/orders/\(id)")
            await MainActor.run {
                orders.removeAll { $0.id == id }
                showToast("Order cancelled")
            }
        } catch {
            await MainActor.run { showToast("Failed to cancel") }
        }
    }

    func showToast(_ msg: String) {
        withAnimation { toast = msg }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation { toast = nil }
        }
    }

    func formatDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = f.date(from: iso) else { return iso }
        let df = DateFormatter()
        df.dateStyle = .none
        df.timeStyle = .short
        return df.string(from: date)
    }

    func load() async {
        do {
            let resp = try await APIService.shared.fetch("/api/orders?limit=100", as: OrdersResponse.self)
            await MainActor.run {
                orders = resp.orders ?? []
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
