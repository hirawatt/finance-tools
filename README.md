# Finance-Tools 📊

A collection of financial analysis tools to help investors make data-driven decisions.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://finance-tools.streamlit.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/hirawatt?label=GitHub%20Sponsors&style=social)](https://github.com/sponsors/hirawatt)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Last Commit](https://img.shields.io/github/last-commit/hirawatt/finance-tools)](https://github.com/hirawatt/finance-tools)

## 🌟 Featured Tools

### 1. Zerodha Leaderboards

Track top performers using [Verified PnL](https://support.zerodha.com/category/console/reports/other-queries/articles/verified-p-l)
📈 **Live Demo**: [zerodha.hirawat.in](https://zerodha.hirawat.in/)

### 2. Co-Pilot: Portfolio Analyzer

An intelligent portfolio management system that provides comprehensive analysis and optimization suggestions for your investments.

#### Key Features

- 📊 Portfolio Analysis
- 🎯 Risk Assessment
- 📈 Performance Tracking
- 🔄 Rebalancing Suggestions
- 📉 Risk Management

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/hirawatt/finance-tools.git

# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py
```

## 🗺️ Roadmap

### Portfolio Analyzer

- [x] Integration with [quantstats](https://github.com/ranaroussi/quantstats)
- [ ] Advanced Portfolio Analytics
  - [x] Sector & Stock Weightage
  - [x] Portfolio Beta Calculation
  - [ ] PE Ratio Analysis
  - [x] Correlation Matrix
- [ ] Risk Management
  - [ ] ASM/GSM List Monitoring
  - [ ] Default Probability Assessment
  - [ ] Automated Rebalancing Suggestions
- [ ] Market Intelligence
  - [ ] Earnings Calendar
  - [ ] Price Forecasting
  - [ ] Red Flag Detection 🚩

## 📊 Portfolio Analysis Flow

```mermaid
graph TD;
    A(Co-Pilot) --> B(Analyze) & C(Optimize)
    B --> D(Sector Weightage) & E(Stock Weightage)
    C --> F(Rebalance) & G(Reduce Risk) & H(Maximize Returns)
    G & H --> I(Sharpe Ratio & Treynor Ratio Comparison)
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 💝 Support the Project

If you find this project useful, consider supporting its development:

- [GitHub Sponsors](https://github.com/sponsors/hirawatt)
- <a href="https://www.buymeacoffee.com/hirawat" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="100" height="25" ></a>

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
