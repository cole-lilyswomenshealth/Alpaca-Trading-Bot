import SwiftUI

struct SettingsInputsView: View {
    @State private var settings: AppSettings?
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var toast: String?

    // Editable state
    @State private var tradingEnabled = true
    @State private var fibEnabled = true
    @State private var profitProtection = true
    @State private var fibBase = "1.0"
    @State private var fibMax = "10"
    @State private var maxPos = "10000"
    @State private var maxLoss = "500"
    @State private var maxOpen = "10"
    @State private var profitThreshold = "0.0"

    let maroon = Color(red: 0.5, green: 0, blue: 0.125)

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    Form {
                        Section("Trading Controls") {
                            Toggle("Trading Enabled", isOn: $tradingEnabled)
                                .tint(maroon)
                            Toggle("Fibonacci Sizing", isOn: $fibEnabled)
                                .tint(maroon)
                            Toggle("Profit Protection", isOn: $profitProtection)
                                .tint(maroon)
                        }

                        Section("Fibonacci Position Sizing") {
                            LabeledContent("Base Quantity") {
                                TextField("1.0", text: $fibBase)
                                    .keyboardType(.decimalPad)
                                    .multilineTextAlignment(.trailing)
                            }
                            LabeledContent("Max Steps") {
                                TextField("10", text: $fibMax)
                                    .keyboardType(.numberPad)
                                    .multilineTextAlignment(.trailing)
                            }
                        }

                        Section("Profit Protection") {
                            LabeledContent("Min Profit % to Sell") {
                                TextField("0.0", text: $profitThreshold)
                                    .keyboardType(.decimalPad)
                                    .multilineTextAlignment(.trailing)
                            }
                        }

                        Section("Risk Management") {
                            LabeledContent("Max Position Size ($)") {
                                TextField("10000", text: $maxPos)
                                    .keyboardType(.decimalPad)
                                    .multilineTextAlignment(.trailing)
                            }
                            LabeledContent("Max Open Positions") {
                                TextField("10", text: $maxOpen)
                                    .keyboardType(.numberPad)
                                    .multilineTextAlignment(.trailing)
                            }
                            LabeledContent("Max Daily Loss ($)") {
                                TextField("500", text: $maxLoss)
                                    .keyboardType(.decimalPad)
                                    .multilineTextAlignment(.trailing)
                            }
                        }

                        Section {
                            Button {
                                Task { await save() }
                            } label: {
                                HStack {
                                    if isSaving { ProgressView().tint(.white) }
                                    Text(isSaving ? "Saving..." : "Save Settings")
                                        .frame(maxWidth: .infinity)
                                        .font(.headline)
                                }
                            }
                            .listRowBackground(maroon)
                            .foregroundStyle(.white)
                            .disabled(isSaving)
                        }
                    }
                }
            }
            .navigationTitle("Settings")
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

    func load() async {
        do {
            let resp = try await APIService.shared.fetch("/api/settings", as: SettingsResponse.self)
            await MainActor.run {
                if let s = resp.settings {
                    tradingEnabled = s.trading_enabled ?? true
                    fibEnabled = s.fibonacci_enabled ?? true
                    profitProtection = s.profit_protection_enabled ?? true
                    fibBase = String(s.fibonacci_base ?? 1.0)
                    fibMax = String(s.fibonacci_max_iterations ?? 10)
                    maxPos = String(s.max_position_size ?? 10000)
                    maxLoss = String(s.max_daily_loss ?? 500)
                    maxOpen = String(s.max_open_positions ?? 10)
                    profitThreshold = String(s.profit_protection_threshold ?? 0)
                }
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    func save() async {
        isSaving = true
        let body: [String: Any] = [
            "trading_enabled": tradingEnabled,
            "fibonacci_enabled": fibEnabled,
            "profit_protection_enabled": profitProtection,
            "fibonacci_base": Double(fibBase) ?? 1.0,
            "fibonacci_max_iterations": Int(fibMax) ?? 10,
            "max_position_size": Double(maxPos) ?? 10000,
            "max_daily_loss": Double(maxLoss) ?? 500,
            "max_open_positions": Int(maxOpen) ?? 10,
            "profit_protection_threshold": Double(profitThreshold) ?? 0
        ]
        do {
            _ = try await APIService.shared.post("/api/settings", body: body, as: SettingsResponse.self)
            await MainActor.run {
                isSaving = false
                showToast("Settings saved")
            }
        } catch {
            await MainActor.run {
                isSaving = false
                showToast("Failed to save")
            }
        }
    }

    func showToast(_ msg: String) {
        withAnimation { toast = msg }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            withAnimation { toast = nil }
        }
    }
}
