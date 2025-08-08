import requests
from typing import List

MORPHO_GRAPHQL_URL = "https://api.morpho.org/graphql"

def get_felix_supply_apy() -> str:
    query = """
    query {
      markets(where: { chainId_in: [8453] }) {
        items {
          loanAsset {
            symbol
            address
          }
          state {
            supplyApy
          }
        }
      }
    }
    """

    tracked_assets = {"USDe", "USD₮0", "HYPE"}
    try:
        response = requests.post(
            MORPHO_GRAPHQL_URL,
            json={"query": query},
            timeout=10  # seconds
        )
        response.raise_for_status()
        result = response.json()

        apy_data = result.get("data", {}).get("markets", {}).get("items", [])
        if not apy_data:
            return "No market data returned."

        filtered_data: List[str] = []

        for item in apy_data:
            loan_asset = item.get("loanAsset", {})
            state = item.get("state", {})
            symbol = loan_asset.get("symbol")
            apy = state.get("supplyApy")

            if symbol in tracked_assets and apy is not None:
                filtered_data.append(
                    f"🔹 {symbol}\n   🔼 Supply APY: {apy * 100:.2f}%"
                )

        return "\n\n".join(filtered_data) if filtered_data else "No data for specified assets."

    except requests.exceptions.RequestException as req_err:
        return f"Network error fetching Felix APY: {req_err}"
    except Exception as e:
        return f"Unexpected error: {e}"

if __name__ == "__main__":
    print("📊 Felix (Morpho) Supply APY\n")
    print(get_felix_supply_apy())
