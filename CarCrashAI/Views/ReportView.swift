import SwiftUI

// MARK: - ReportView

struct ReportView: View {
    @Bindable var viewModel: AnalysisViewModel

    private let currencyFormatter: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = "USD"
        return f
    }()

    var body: some View {
        Group {
            if let report = viewModel.report {
                reportContent(report)
            } else {
                ContentUnavailableView(
                    "No Report",
                    systemImage: "doc.questionmark",
                    description: Text("Run an analysis to generate a report.")
                )
            }
        }
        .navigationTitle("Report")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                ShareLink(
                    item: reportText,
                    subject: Text("Car Crash AI Report"),
                    message: Text("Vehicle damage assessment report")
                )
                .disabled(viewModel.report == nil)
                .accessibilityLabel("Share report")
            }
        }
    }

    // MARK: - Report Content

    private func reportContent(_ report: AssessmentReport) -> some View {
        List {
            vehicleSection(report.vehicle)
            damageSection(report.damages)
            costSection(report.estimates)
            totalsSection(report.totals)
        }
        .listStyle(.insetGrouped)
    }

    // MARK: - Vehicle Info

    private func vehicleSection(_ vehicle: Vehicle) -> some View {
        Section("Vehicle Information") {
            LabeledContent("Make", value: vehicle.make)
            LabeledContent("Model", value: vehicle.model)
            LabeledContent("Year", value: "\(vehicle.year)")

            if let color = vehicle.color {
                LabeledContent("Color", value: color)
            }
            if let body = vehicle.bodyStyle {
                LabeledContent("Body Style", value: body)
            }

            confidenceRow(vehicle.confidence)
        }
    }

    private func confidenceRow(_ confidence: Double) -> some View {
        HStack {
            Text("Confidence")
            Spacer()
            Text("\(Int(confidence * 100))%")
                .foregroundStyle(confidence >= 0.7 ? .green : .orange)
                .fontWeight(.semibold)
        }
        .accessibilityLabel("Confidence \(Int(confidence * 100)) percent")
    }

    // MARK: - Damage Assessment

    private func damageSection(_ damages: [DamageItem]) -> some View {
        Section("Damage Assessment") {
            if damages.isEmpty {
                Text("No damage detected.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(damages) { damage in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(Components.displayName(damage.component))
                                .font(.headline)
                            Spacer()
                            Text(damage.recommendation.rawValue.capitalized)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(damage.recommendation == .replace ? Color.red.opacity(0.15) : Color.orange.opacity(0.15))
                                .foregroundStyle(damage.recommendation == .replace ? .red : .orange)
                                .clipShape(Capsule())
                        }

                        Text(damage.description)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)

                        severityBar(damage.severity)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private func severityBar(_ severity: Double) -> some View {
        HStack(spacing: 8) {
            Text("Severity")
                .font(.caption)
                .foregroundStyle(.secondary)

            ProgressView(value: severity, total: 1.0)
                .tint(severityColor(severity))

            Text("\(Int(severity * 100))%")
                .font(.caption.monospacedDigit())
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

    // MARK: - Cost Breakdown

    private func costSection(_ estimates: [CostEstimate]) -> some View {
        Section("Cost Breakdown") {
            if estimates.isEmpty {
                Text("No cost estimates available.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(estimates) { estimate in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(Components.displayName(estimate.component))
                            .font(.headline)

                        HStack {
                            Text("Parts")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatCurrency(estimate.partCostAvg))
                        }
                        .font(.subheadline)

                        HStack {
                            Text("Labor (\(formatDecimal(estimate.laborHours))h)")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formatCurrency(estimate.laborCost))
                        }
                        .font(.subheadline)

                        HStack {
                            Text("Subtotal")
                                .fontWeight(.semibold)
                            Spacer()
                            Text(formatCurrency(estimate.totalAvg))
                                .fontWeight(.semibold)
                        }
                        .font(.subheadline)

                        Text(estimate.pricingMethod.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    // MARK: - Totals

    private func totalsSection(_ totals: AssessmentReport.Totals) -> some View {
        Section("Total Estimate") {
            LabeledContent("Parts Total", value: formatCurrency(totals.partsTotal))
            LabeledContent("Labor Total", value: formatCurrency(totals.laborTotal))

            HStack {
                Text("Grand Total")
                    .font(.headline)
                Spacer()
                Text(formatCurrency(totals.grandTotal))
                    .font(.headline)
                    .foregroundStyle(.blue)
            }
        }
    }

    // MARK: - Formatting

    private func formatCurrency(_ value: Decimal) -> String {
        currencyFormatter.string(from: value as NSDecimalNumber) ?? "$0.00"
    }

    private func formatDecimal(_ value: Decimal) -> String {
        NSDecimalNumber(decimal: value).stringValue
    }

    // MARK: - Share Text

    private var reportText: String {
        guard let report = viewModel.report else { return "" }
        var lines: [String] = []
        lines.append("Car Crash AI — Damage Report")
        lines.append("============================")
        lines.append("")
        lines.append("Vehicle: \(report.vehicle.year) \(report.vehicle.make) \(report.vehicle.model)")
        if let color = report.vehicle.color { lines.append("Color: \(color)") }
        lines.append("")
        lines.append("Damages:")
        for d in report.damages {
            lines.append("  • \(Components.displayName(d.component)) — \(d.damageType) (severity: \(Int(d.severity * 100))%)")
        }
        lines.append("")
        lines.append("Cost Estimates:")
        for e in report.estimates {
            lines.append("  • \(Components.displayName(e.component)): \(formatCurrency(e.totalAvg))")
        }
        lines.append("")
        lines.append("Grand Total: \(formatCurrency(report.totals.grandTotal))")
        return lines.joined(separator: "\n")
    }
}
