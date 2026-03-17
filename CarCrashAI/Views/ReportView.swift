import SwiftUI

// MARK: - ReportView

struct ReportView: View {
    let report: AssessmentReport

    private let currencyFormatter: NumberFormatter = {
        let fmt = NumberFormatter()
        fmt.numberStyle = .currency
        fmt.currencyCode = "USD"
        return fmt
    }()

    var body: some View {
        List {
            vehicleSection
            damageSection
            costSection
            totalsSection
            disclaimerSection
        }
        .navigationTitle("Assessment Report")
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: - Vehicle Info

    private var vehicleSection: some View {
        Section("Vehicle") {
            LabeledContent("Make", value: report.vehicle.make)
            LabeledContent("Model", value: report.vehicle.model)
            LabeledContent("Year", value: "\(report.vehicle.year)")
            if let bodyStyle = report.vehicle.bodyStyle {
                LabeledContent("Body Style", value: bodyStyle.capitalized)
            }
            if let color = report.vehicle.color {
                LabeledContent("Color", value: color.capitalized)
            }
            LabeledContent("Confidence") {
                Text("\(Int(report.vehicle.confidence * 100))%")
                    .foregroundStyle(report.vehicle.confidence >= 0.7 ? .primary : .orange)
            }
        }
    }

    // MARK: - Damage Assessment

    private var damageSection: some View {
        Section("Damage Detected (\(report.damages.count))") {
            if report.damages.isEmpty {
                Text("No damage detected.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(report.damages) { damage in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(Components.displayName(damage.component))
                                .font(.headline)
                            Spacer()
                            Text(damage.recommendation == .replace ? "Replace" : "Repair")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(damage.recommendation == .replace ? Color.red.opacity(0.15) : Color.green.opacity(0.15))
                                .foregroundStyle(damage.recommendation == .replace ? .red : .green)
                                .clipShape(Capsule())
                        }

                        Text(damage.description)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)

                        HStack {
                            Text(damage.damageType.capitalized)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            severityBar(damage.severity)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    // MARK: - Cost Breakdown

    private var costSection: some View {
        Section("Cost Breakdown") {
            if report.estimates.isEmpty {
                Text("No cost estimates available.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(report.estimates) { estimate in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(Components.displayName(estimate.component))
                            .font(.headline)

                        HStack {
                            Text("Parts:")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatRange(low: estimate.partCostLow, high: estimate.partCostHigh))
                        }
                        .font(.subheadline)

                        HStack {
                            Text("Labor (\(formatDecimal(estimate.laborHours))h × \(formatCurrency(estimate.laborRate))/h):")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatCurrency(estimate.laborCost))
                        }
                        .font(.subheadline)

                        HStack {
                            Text("Subtotal:")
                                .fontWeight(.medium)
                            Spacer()
                            Text(formatCurrency(estimate.totalAvg))
                                .fontWeight(.medium)
                        }
                        .font(.subheadline)

                        if estimate.pricingMethod != .liveSearch {
                            Text(pricingMethodLabel(estimate.pricingMethod))
                                .font(.caption2)
                                .foregroundStyle(.orange)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    // MARK: - Totals

    private var totalsSection: some View {
        Section("Total Estimate") {
            LabeledContent("Parts Total", value: formatCurrency(report.totals.partsTotal))
            LabeledContent("Labor Total", value: formatCurrency(report.totals.laborTotal))
            LabeledContent("Grand Total") {
                Text(formatCurrency(report.totals.grandTotal))
                    .fontWeight(.bold)
                    .font(.title3)
            }
        }
    }

    // MARK: - Disclaimer

    private var disclaimerSection: some View {
        Section {
            Text("This is an AI-generated estimate for informational purposes only. Actual repair costs may vary. Consult a certified mechanic or body shop for an accurate quote.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Helpers

    private func severityBar(_ severity: Double) -> some View {
        HStack(spacing: 4) {
            ProgressView(value: severity)
                .tint(severityColor(severity))
                .frame(width: 80)
            Text(String(format: "%.0f%%", severity * 100))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityLabel("Severity \(Int(severity * 100)) percent")
    }

    private func severityColor(_ severity: Double) -> Color {
        switch severity {
        case ..<0.3: .green
        case 0.3..<0.6: .yellow
        case 0.6..<0.8: .orange
        default: .red
        }
    }

    private func formatCurrency(_ value: Decimal) -> String {
        currencyFormatter.string(from: value as NSDecimalNumber) ?? "$\(value)"
    }

    private func formatDecimal(_ value: Decimal) -> String {
        "\(NSDecimalNumber(decimal: value).doubleValue)"
    }

    private func formatRange(low: Decimal, high: Decimal) -> String {
        "\(formatCurrency(low)) – \(formatCurrency(high))"
    }

    private func pricingMethodLabel(_ method: CostEstimate.PricingMethod) -> String {
        switch method {
        case .liveSearch: "Live pricing"
        case .staticReference: "⚠ Based on reference data"
        case .aiEstimate: "⚠ AI-estimated pricing"
        case .defaultFallback: "⚠ Default estimate — verify pricing"
        }
    }
}
