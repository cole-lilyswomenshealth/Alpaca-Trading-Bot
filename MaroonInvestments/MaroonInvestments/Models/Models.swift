import Foundation

// MARK: - Account
struct AccountResponse: Decodable {
    let success: Bool
    let account: AccountData?
    let positions: [Position]?
    let total_positions: Int?
}

struct AccountData: Decodable {
    let equity: String
    let buying_power: String
    let cash: String
    let last_equity: String
    let status: String
    let portfolio_value: String

    var equityDouble: Double { Double(equity) ?? 0 }
    var buyingPowerDouble: Double { Double(buying_power) ?? 0 }
    var lastEquityDouble: Double { Double(last_equity) ?? 0 }
    var dayPL: Double { equityDouble - lastEquityDouble }
}

// MARK: - Position
struct Position: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let qty: Double
    let avg_entry_price: Double
    let current_price: Double
    let market_value: Double
    let unrealized_pl: Double
    let unrealized_plpc: Double
    let side: String
}

// MARK: - Order
struct OrdersResponse: Decodable {
    let orders: [Order]?
}

struct Order: Decodable, Identifiable {
    let id: String
    let symbol: String
    let qty: Double
    let filled_qty: Double?
    let side: String
    let type: String
    let status: String
    let filled_avg_price: Double?
    let limit_price: Double?
    let submitted_at: String?
    let filled_at: String?
}

// MARK: - Option Chain
struct ChainResponse: Decodable {
    let success: Bool
    let chain: [OptionContract]?
    let expirations: [String]?
    let underlying_price: Double?
    let selected_expiration: String?
    let error: String?
}

struct OptionContract: Decodable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let name: String
    let strike: Double
    let expiration: String
    let type: String
    let bid: Double?
    let ask: Double?
    let last: Double?
    let volume: Double?
    let open_interest: String?
}

// MARK: - Settings
struct SettingsResponse: Decodable {
    let success: Bool
    let settings: AppSettings?
}

struct AppSettings: Decodable {
    let trading_enabled: Bool?
    let fibonacci_enabled: Bool?
    let fibonacci_base: Double?
    let fibonacci_max_iterations: Int?
    let max_position_size: Double?
    let max_daily_loss: Double?
    let max_open_positions: Int?
    let profit_protection_enabled: Bool?
    let profit_protection_threshold: Double?
}

// MARK: - Order Result
struct OrderResult: Decodable {
    let success: Bool
    let order_id: String?
    let symbol: String?
    let status: String?
    let error: String?
}

// MARK: - Closed Positions
struct ClosedResponse: Decodable {
    let success: Bool
    let positions: [ClosedPosition]?
}

struct ClosedPosition: Decodable, Identifiable {
    var id: String { (symbol) + (closed_at ?? "") }
    let symbol: String
    let qty: Double
    let open_price: Double
    let close_price: Double
    let pnl: Double
    let pnl_pct: Double
    let closed_at: String?
}
