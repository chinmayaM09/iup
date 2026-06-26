"""
CAS Number → IUPAC Chemical Names
---------------------------------
A Streamlit application that takes a CAS Registry Number and returns
all possible IUPAC chemical names by querying the PubChem REST API.
"""

import re
import time
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PUBCHEM_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
REQUEST_TIMEOUT = 30  # seconds
RATE_LIMIT_DELAY = 0.25  # ~4 requests/sec to stay below PubChem's 5 req/s limit

st.set_page_config(
    page_title="CAS → IUPAC Names",
    page_icon="🧪",
    layout="wide",
)


# -----------------------------------------------------------------------------
# CAS Validation
# -----------------------------------------------------------------------------
def is_valid_cas_format(cas: str) -> bool:
    """Check that the CAS number follows the format NNNN-NN-N."""
    return bool(re.match(r"^\d{2,7}-\d{2}-\d$", cas))


def validate_cas_check_digit(cas: str) -> bool:
    """Validate the CAS check digit using the standard algorithm."""
    digits = cas.replace("-", "")[:-1]
    check_digit = int(cas[-1])
    total = sum(int(d) * (len(digits) - i) for i, d in enumerate(digits))
    return total % 10 == check_digit


# -----------------------------------------------------------------------------
# PubChem Helpers
# -----------------------------------------------------------------------------
def get_cids_from_cas(cas: str):
    """Return a list of PubChem CIDs for a given CAS number."""
    url = f"{PUBCHEM_REST}/compound/name/{cas}/cids/JSON"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return data.get("IdentifierList", {}).get("CID", [])
        if r.status_code == 404:
            return []
        r.raise_for_status()
    except requests.RequestException as e:
        st.error(f"Error contacting PubChem: {e}")
    return []


def get_properties(cid: int) -> dict:
    """Fetch key properties for a CID."""
    props = "MolecularFormula,MolecularWeight,IUPACName,CanonicalSMILES,InChIKey"
    url = f"{PUBCHEM_REST}/compound/cid/{cid}/property/{props}/JSON"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            props_list = data.get("PropertyTable", {}).get("Properties", [])
            if props_list:
                return props_list[0]
    except requests.RequestException:
        pass
    return {}


def get_synonyms(cid: int):
    """Fetch the full synonym list for a CID."""
    url = f"{PUBCHEM_REST}/compound/cid/{cid}/synonyms/JSON"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            info_list = data.get("InformationList", {}).get("Information", [])
            if info_list:
                return info_list[0].get("Synonym", [])
    except requests.RequestException:
        pass
    return []


def extract_iupac_names(synonyms):
    """
    Pull out IUPAC-tagged entries from PubChem's synonym list.

    PubChem formats them as:
        "IUPAC Name: methane"
        "IUPAC Name (Preferred): ..."
        "IUPAC Name (Systematic): ..."
        "IUPAC Name (Traditional): ..."
        "IUPAC Name (CAS): ..."
        "IUPAC Name (Allowed): ..."
    """
    pattern = re.compile(r"^IUPAC Name(?:\s*\([^)]+\))?\s*:\s*(.+)$", re.IGNORECASE)
    names = []
    seen = set()
    for syn in synonyms:
        m = pattern.match(syn)
        if m:
            name = m.group(1).strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
    return names


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
def main():
    st.title("🧪 CAS Number → IUPAC Chemical Names")
    st.markdown(
        "Enter a **CAS Registry Number** to retrieve every available "
        "**IUPAC chemical name** (Preferred, Systematic, Traditional, CAS, "
        "Allowed, etc.) from PubChem."
    )

    # --- Input row ---
    col1, col2 = st.columns([3, 1])
    with col1:
        cas_input = st.text_input(
            "CAS Number",
            placeholder="e.g., 50-00-0 (formaldehyde)",
        )
    with col2:
        check_digit = st.checkbox("Validate check digit", value=True)

    # --- Example buttons ---
    st.markdown("**Try an example:**")
    examples = ["50-00-0", "67-56-1", "64-17-5", "7732-18-5", "79-34-5"]
    ex_cols = st.columns(len(examples))
    for col, ex in zip(ex_cols, examples):
        if col.button(ex, key=f"ex_{ex}"):
            cas_input = ex
            st.rerun()

    if st.button("🔍 Search", type="primary"):
        cas_input = cas_input.strip()

        # --- Validation ---
        if not cas_input:
            st.warning("Please enter a CAS number.")
            return
        if not is_valid_cas_format(cas_input):
            st.error("❌ Invalid CAS format. Expected: `NNNN-NN-N` (e.g., `50-00-0`).")
            return
        if check_digit and not validate_cas_check_digit(cas_input):
            st.error("❌ Invalid CAS number — check digit does not match.")
            return

        # --- Lookup ---
        with st.spinner("Querying PubChem…"):
            cids = get_cids_from_cas(cas_input)

            if not cids:
                st.error(f"No PubChem compound found for CAS **{cas_input}**.")
                st.info(
                    "Possible reasons: the CAS is not indexed in PubChem, "
                    "the number is incorrect, or it refers to a substance "
                    "without a single defined structure."
                )
                return

            st.success(f"✅ Found {len(cids)} compound(s) for CAS **{cas_input}**")

            for idx, cid in enumerate(cids, 1):
                time.sleep(RATE_LIMIT_DELAY)
                props = get_properties(cid)
                time.sleep(RATE_LIMIT_DELAY)
                synonyms = get_synonyms(cid)
                iupac_names = extract_iupac_names(synonyms)

                # Use the property IUPAC name as a fallback / primary
                pref = props.get("IUPACName")
                if pref and pref not in iupac_names:
                    iupac_names.insert(0, pref)

                with st.container(border=True):
                    st.subheader(f"Result {idx} — PubChem CID {cid}")

                    # Property metrics
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Molecular Formula", props.get("MolecularFormula", "—"))
                    c2.metric(
                        "Molecular Weight",
                        f"{props.get('MolecularWeight', '—')} g/mol",
                    )
                    c3.metric("InChIKey", props.get("InChIKey", "—"))

                    if props.get("CanonicalSMILES"):
                        st.code(
                            f"SMILES: {props['CanonicalSMILES']}", language="text"
                        )

                    st.markdown(
                        f"🔗 [View full record on PubChem "
                        f"(CID {cid})](https://pubchem.ncbi.nlm.nih.gov/compound/{cid})"
                    )

                    # --- IUPAC names ---
                    st.markdown("### 📋 IUPAC Chemical Names")
                    if iupac_names:
                        for i, name in enumerate(iupac_names, 1):
                            tag = " *(preferred)*" if i == 1 and pref else ""
                            st.markdown(f"**{i}.** `{name}`{tag}")

                        # Download
                        txt = "\n".join(iupac_names)
                        st.download_button(
                            label="📥 Download names (.txt)",
                            data=txt,
                            file_name=f"iupac_names_{cas_input.replace('-', '_')}_cid{cid}.txt",
                            mime="text/plain",
                            key=f"dl_{cid}",
                        )
                    else:
                        st.info("No IUPAC names are available for this compound.")

                    # --- All synonyms ---
                    with st.expander(f"Show all {len(synonyms)} synonyms"):
                        for s in synonyms:
                            st.write(s)


if __name__ == "__main__":
    main()
