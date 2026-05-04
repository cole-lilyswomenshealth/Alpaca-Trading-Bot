import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            PortfolioView()
                .tabItem {
                    Label("Portfolio", systemImage: "chart.line.uptrend.xyaxis")
                }

            PositionsView()
                .tabItem {
                    Label("Positions", systemImage: "clock.fill")
                }

            TradeView()
                .tabItem {
                    Label("Trade", systemImage: "arrow.up.arrow.down.circle.fill")
                }

            OrdersView()
                .tabItem {
                    Label("Orders", systemImage: "list.clipboard.fill")
                }

            SettingsInputsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
        }
        .tint(Color(red: 0.5, green: 0, blue: 0.125)) // Maroon
    }
}
