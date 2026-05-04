import SwiftUI

struct TradeView: View {
    @State private var selectedTab = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Trade Type", selection: $selectedTab) {
                    Text("Stocks").tag(0)
                    Text("Options").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()

                if selectedTab == 0 {
                    StockOrderView()
                } else {
                    OptionChainView()
                }
            }
            .navigationTitle("Trade")
            .background(Color(.systemGroupedBackground))
        }
    }
}

// MARK: - Stock Order
struct StockOrderView: View {
    @State private var symbol = ""
    @State private var qty = ""
    @State private var side = "buy"
    @State private var orderType = "market"
    @State private var price = ""
    @State private var result: String?
    @State private var resultOk = true
    @State private var isSubmitting = false

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Form card
                VStack(spacing: 0) {
                    formRow {
                        TextField("Symbol (AAPL, TSLA...)", text: $symbol)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.characters)
                    }
                    Divider().padding(.leading)
                    formRow {
                        Picker("Side", selection: $side) {
                            Text("Buy / Long").tag("buy")
                            Text("Sell / Short").tag("sell")
                        }
                    }
                    Divider().padding(.leading)
                    formRow {
                        TextField("Quantity", text: $qty)
                            .keyboardType(.decimalPad)
                    }
                    Divider().padding(.leading)
                    formRow {
                        Picker("Order Type", selection: $orderType) {
                            Text("Market").tag("market")
                            Text("Limit").tag("limit")
                            Text("Stop").tag("stop")
                        }
                    }
                    if orderType != "market" {
                        Divider().padding(.leading)
                        formRow {
                            TextField("Price", text: $price)
                                .keyboardType(.decimalPad)
                        }
                    }
                }
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                // Result
                if let result {
                    Text(result)
                        .font(.subheadline)
                        .foregroundStyle(resultOk ? .green : .red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                }

                // Submit
                Button {
                    Task { await submit() }
                } label: {
                    HStack {
                        if isSubmitting { ProgressView().tint(.white) }
                        Text(isSubmitting ? "Placing..." : "Place Order")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(maroon)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(isSubmitting)
            }
            .padding()
        }
    }

    func formRow<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        HStack {
            content()
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
    }

    func submit() async {
        guard !symbol.isEmpty, let qtyVal = Double(qty) else {
            result = "Enter a symbol and quantity"
            resultOk = false
            return
        }
        isSubmitting = true
        var body: [String: Any] = ["symbol": symbol.uppercased(), "action": side, "qty": qtyVal, "order_type": orderType]
        if orderType != "market", let p = Double(price) { body["price"] = p }

        do {
            let resp = try await APIService.shared.post("/api/order", body: body, as: OrderResult.self)
            await MainActor.run {
                if resp.success {
                    result = "✓ \(side.uppercased()) \(qtyVal, specifier: "%.0f") \(symbol.uppercased()) — \(resp.status ?? "submitted")"
                    resultOk = true
                    symbol = ""; qty = ""; price = ""
                } else {
                    result = resp.error ?? "Order failed"
                    resultOk = false
                }
                isSubmitting = false
            }
        } catch {
            await MainActor.run {
                result = error.localizedDescription
                resultOk = false
                isSubmitting = false
            }
        }
    }
}

// MARK: - Option Chain
struct OptionChainView: View {
    @State private var symbol = "SPY"
    @State private var expirations: [String] = []
    @State private var selectedExp = ""
    @State private var chainType = "call"
    @State private var chain: [OptionContract] = []
    @State private var underlyingPrice: Double?
    @State private var isLoading = false
    @State private var selectedContract: OptionContract?
    @State private var showOrderSheet = false

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        VStack(spacing: 0) {
            // Controls
            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    TextField("Symbol", text: $symbol)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.characters)
                        .padding(10)
                        .background(Color(.secondarySystemGroupedBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .frame(maxWidth: 100)

                    if !expirations.isEmpty {
                        Picker("Expiration", selection: $selectedExp) {
                            ForEach(expirations, id: \.self) { Text($0).tag($0) }
                        }
                        .pickerStyle(.menu)
                        .padding(8)
                        .background(Color(.secondarySystemGroupedBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .onChange(of: selectedExp) { _, _ in Task { await loadChain() } }
                    }

                    Spacer()

                    Button {
                        Task { await loadExpirations() }
                    } label: {
                        Text("Load")
                            .font(.subheadline.weight(.semibold))
                            .padding(.horizontal, 14).padding(.vertical, 8)
                            .background(maroon)
                            .foregroundStyle(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                }

                Picker("Type", selection: $chainType) {
                    Text("Calls").tag("call")
                    Text("Puts").tag("put")
                }
                .pickerStyle(.segmented)
                .onChange(of: chainType) { _, _ in
                    expirations = []
                    selectedExp = ""
                    chain = []
                }

                if let price = underlyingPrice {
                    Text("\(symbol) @ \(price, format: .currency(code: "USD"))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding()
            .background(Color(.systemGroupedBackground))

            if isLoading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if chain.isEmpty {
                ContentUnavailableView("Enter a symbol and tap Load", systemImage: "chart.bar.doc.horizontal")
            } else {
                // Chain table
                List(chain) { contract in
                    Button {
                        selectedContract = contract
                        showOrderSheet = true
                    } label: {
                        chainRow(contract)
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.plain)
            }
        }
        .sheet(item: $selectedContract) { contract in
            OptionOrderSheet(contract: contract)
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
        }
    }

    func chainRow(_ c: OptionContract) -> some View {
        let atm = underlyingPrice.map { abs(c.strike - $0) < 1.0 } ?? false
        return HStack {
            Text(c.strike, format: .number)
                .font(.system(size: 14, weight: atm ? .bold : .regular))
                .foregroundStyle(atm ? maroon : .primary)
                .frame(width: 60, alignment: .leading)
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                HStack(spacing: 12) {
                    Text(c.bid.map { String(format: "$%.2f", $0) } ?? "—")
                        .foregroundStyle(.green)
                    Text(c.ask.map { String(format: "$%.2f", $0) } ?? "—")
                        .foregroundStyle(.red)
                }
                .font(.system(size: 13))
                Text("Vol: \(c.volume.map { Int($0).formatted() } ?? "—")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
        .background(atm ? maroon.opacity(0.05) : .clear)
    }

    func loadExpirations() async {
        isLoading = true
        do {
            let resp = try await APIService.shared.fetch(
                "/api/options/chain?symbol=\(symbol)&type=\(chainType)&expirations_only=true",
                as: ChainResponse.self
            )
            await MainActor.run {
                expirations = resp.expirations ?? []
                selectedExp = expirations.first ?? ""
                isLoading = false
            }
            if !selectedExp.isEmpty { await loadChain() }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    func loadChain() async {
        guard !selectedExp.isEmpty else { return }
        isLoading = true
        do {
            let path = "/api/options/chain?symbol=\(symbol)&type=\(chainType)&expiration=\(selectedExp)"
            let resp = try await APIService.shared.fetch(path, as: ChainResponse.self)
            await MainActor.run {
                chain = resp.chain ?? []
                underlyingPrice = resp.underlying_price
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}

// MARK: - Option Order Sheet
struct OptionOrderSheet: View {
    let contract: OptionContract
    @State private var side = "buy"
    @State private var qty = "1"
    @State private var orderType = "market"
    @State private var limitPrice = ""
    @State private var result: String?
    @State private var resultOk = true
    @State private var isSubmitting = false
    @Environment(\.dismiss) var dismiss

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        NavigationStack {
            Form {
                Section("Contract") {
                    LabeledContent("Symbol", value: contract.symbol)
                    LabeledContent("Strike", value: contract.strike, format: .number)
                    LabeledContent("Expiration", value: contract.expiration)
                    LabeledContent("Bid / Ask") {
                        HStack {
                            Text(contract.bid.map { String(format: "$%.2f", $0) } ?? "—").foregroundStyle(.green)
                            Text("/")
                            Text(contract.ask.map { String(format: "$%.2f", $0) } ?? "—").foregroundStyle(.red)
                        }
                    }
                }

                Section("Order") {
                    Picker("Side", selection: $side) {
                        Text("Buy").tag("buy")
                        Text("Sell").tag("sell")
                    }
                    .pickerStyle(.segmented)

                    TextField("Contracts", text: $qty)
                        .keyboardType(.numberPad)

                    Picker("Order Type", selection: $orderType) {
                        Text("Market").tag("market")
                        Text("Limit").tag("limit")
                    }

                    if orderType == "limit" {
                        TextField("Limit Price", text: $limitPrice)
                            .keyboardType(.decimalPad)
                            .onAppear {
                                if limitPrice.isEmpty {
                                    limitPrice = side == "buy"
                                        ? String(format: "%.2f", contract.ask ?? 0)
                                        : String(format: "%.2f", contract.bid ?? 0)
                                }
                            }
                    }
                }

                if let result {
                    Section {
                        Text(result)
                            .foregroundStyle(resultOk ? .green : .red)
                    }
                }

                Section {
                    Button {
                        Task { await submit() }
                    } label: {
                        HStack {
                            if isSubmitting { ProgressView().tint(.white) }
                            Text(isSubmitting ? "Submitting..." : "Place Order")
                                .frame(maxWidth: .infinity)
                                .font(.headline)
                        }
                    }
                    .listRowBackground(maroon)
                    .foregroundStyle(.white)
                    .disabled(isSubmitting)
                }
            }
            .navigationTitle("Place Option Order")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    func submit() async {
        guard let qtyInt = Int(qty) else { return }
        isSubmitting = true
        var body: [String: Any] = ["symbol": contract.symbol, "qty": qtyInt, "side": side, "order_type": orderType]
        if orderType == "limit", let lp = Double(limitPrice) { body["limit_price"] = lp }

        do {
            let resp = try await APIService.shared.post("/api/options/order", body: body, as: OrderResult.self)
            await MainActor.run {
                if resp.success {
                    result = "✓ \(side.uppercased()) \(qtyInt) \(contract.symbol) — \(resp.status ?? "submitted")"
                    resultOk = true
                } else {
                    result = resp.error ?? "Order failed"
                    resultOk = false
                }
                isSubmitting = false
            }
        } catch {
            await MainActor.run {
                result = error.localizedDescription
                resultOk = false
                isSubmitting = false
            }
        }
    }
}
