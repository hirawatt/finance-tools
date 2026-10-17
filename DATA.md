# Data Guide & Sources

|Data|Source|Used|
|:-:|:-:|:-:|
|Broker holdings|[Zerodha Console](https://console.zerodha.com/portfolio/holdings/), Groww, Dhan and Angel One holdings exports|Yes — read by `utils/brokers/`, resolved to NSE symbols via `data/stock-sector.csv`|
|Depository CAS|[CDSL](https://www.cdslindia.com/) / [NSDL](https://nsdl.co.in/) Consolidated Account Statement (PDF)|Yes — `utils/brokers/cas.py` reads the holdings table across every demat account|
|India Life Expectancy|[macrotrends.net](https://www.macrotrends.net/countries/IND/india/life-expectancy)|Yes — in the portfolio allocation process|
|Stock Sector Data|[Screener Screen - Export](https://www.screener.in/screen/raw/?sort=&order=&source=&query=Market+Capitalization+) and [ValueResearch](https://www.valueresearchonline.com/stocks/selector/?mcap=0to&custom-cols=ret1d%2Cpl52w%2Cph52w%2Cmcap%2Centval)|Yes|
|FPI Sector-wise Investment Data|[NSDL FPI](https://www.fpi.nsdl.co.in/web/StaticReports/Fortnightly_Sector_wise_FII_Investment_Data/FIIInvestSector_May312022.html)|No|
|instruments|[Kite.Trade](https://api.kite.trade/instruments)|Yes|
|Option chain (EOD)|[NSE derivatives reports](https://www.nseindia.com/all-reports-derivatives) — F&O bhavcopy|Yes — `utils/options.py` pivots the UDiFF contract file into a per-strike chain for the Due Diligence screens|
|Traded volume|Yahoo Finance daily bars (stored in the nightly snapshot)|Yes — `utils/volume.py` screens cash-market volume spikes|
|NSE Nifty Small Cap 100| [Nifty Small Cap 100](https://www1.nseindia.com/content/indices/ind_niftysmallcap100list.csv)|Yes|
|All Companies List| [Screener Screens](https://www.screener.in/screens/722948/all-companies-list/)|Yes|
