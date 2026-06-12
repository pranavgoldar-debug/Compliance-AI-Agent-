// All ISO 3166-1 countries (alpha-2 code + name), the single source for the
// jurisdiction picker. Flags render from the code via flagcdn (see
// JurisdictionBadge), so we only store code + name here — no 196 hand-typed
// emoji to drift.
//
// Existing entities use legacy slug codes (india, uk, uae, …) kept in
// JURISDICTIONS (lib/format). `jurisdictionOptions()` MERGES the two: each
// country appears once, preferring the legacy slug where one exists (so old
// data keeps working) and the 2-letter ISO code otherwise. New entities in a
// country without a legacy slug are stamped with the ISO code (≤16 chars, fits
// the DB column).
import { JURISDICTIONS } from "./format";

export interface Country {
  code: string; // ISO 3166-1 alpha-2 (lowercase)
  name: string;
}

export const COUNTRIES: Country[] = [
  { code: "af", name: "Afghanistan" }, { code: "ax", name: "Åland Islands" },
  { code: "al", name: "Albania" }, { code: "dz", name: "Algeria" },
  { code: "as", name: "American Samoa" }, { code: "ad", name: "Andorra" },
  { code: "ao", name: "Angola" }, { code: "ai", name: "Anguilla" },
  { code: "ag", name: "Antigua and Barbuda" }, { code: "ar", name: "Argentina" },
  { code: "am", name: "Armenia" }, { code: "aw", name: "Aruba" },
  { code: "au", name: "Australia" }, { code: "at", name: "Austria" },
  { code: "az", name: "Azerbaijan" }, { code: "bs", name: "Bahamas" },
  { code: "bh", name: "Bahrain" }, { code: "bd", name: "Bangladesh" },
  { code: "bb", name: "Barbados" }, { code: "by", name: "Belarus" },
  { code: "be", name: "Belgium" }, { code: "bz", name: "Belize" },
  { code: "bj", name: "Benin" }, { code: "bm", name: "Bermuda" },
  { code: "bt", name: "Bhutan" }, { code: "bo", name: "Bolivia" },
  { code: "ba", name: "Bosnia and Herzegovina" }, { code: "bw", name: "Botswana" },
  { code: "br", name: "Brazil" }, { code: "io", name: "British Indian Ocean Territory" },
  { code: "bn", name: "Brunei" }, { code: "bg", name: "Bulgaria" },
  { code: "bf", name: "Burkina Faso" }, { code: "bi", name: "Burundi" },
  { code: "cv", name: "Cabo Verde" }, { code: "kh", name: "Cambodia" },
  { code: "cm", name: "Cameroon" }, { code: "ca", name: "Canada" },
  { code: "ky", name: "Cayman Islands" }, { code: "cf", name: "Central African Republic" },
  { code: "td", name: "Chad" }, { code: "cl", name: "Chile" },
  { code: "cn", name: "China" }, { code: "co", name: "Colombia" },
  { code: "km", name: "Comoros" }, { code: "cg", name: "Congo" },
  { code: "cd", name: "Congo (DRC)" }, { code: "ck", name: "Cook Islands" },
  { code: "cr", name: "Costa Rica" }, { code: "ci", name: "Côte d'Ivoire" },
  { code: "hr", name: "Croatia" }, { code: "cu", name: "Cuba" },
  { code: "cw", name: "Curaçao" }, { code: "cy", name: "Cyprus" },
  { code: "cz", name: "Czechia" }, { code: "dk", name: "Denmark" },
  { code: "dj", name: "Djibouti" }, { code: "dm", name: "Dominica" },
  { code: "do", name: "Dominican Republic" }, { code: "ec", name: "Ecuador" },
  { code: "eg", name: "Egypt" }, { code: "sv", name: "El Salvador" },
  { code: "gq", name: "Equatorial Guinea" }, { code: "er", name: "Eritrea" },
  { code: "ee", name: "Estonia" }, { code: "sz", name: "Eswatini" },
  { code: "et", name: "Ethiopia" }, { code: "fj", name: "Fiji" },
  { code: "fi", name: "Finland" }, { code: "fr", name: "France" },
  { code: "gf", name: "French Guiana" }, { code: "pf", name: "French Polynesia" },
  { code: "ga", name: "Gabon" }, { code: "gm", name: "Gambia" },
  { code: "ge", name: "Georgia" }, { code: "de", name: "Germany" },
  { code: "gh", name: "Ghana" }, { code: "gi", name: "Gibraltar" },
  { code: "gr", name: "Greece" }, { code: "gl", name: "Greenland" },
  { code: "gd", name: "Grenada" }, { code: "gp", name: "Guadeloupe" },
  { code: "gu", name: "Guam" }, { code: "gt", name: "Guatemala" },
  { code: "gg", name: "Guernsey" }, { code: "gn", name: "Guinea" },
  { code: "gw", name: "Guinea-Bissau" }, { code: "gy", name: "Guyana" },
  { code: "ht", name: "Haiti" }, { code: "hn", name: "Honduras" },
  { code: "hk", name: "Hong Kong" }, { code: "hu", name: "Hungary" },
  { code: "is", name: "Iceland" }, { code: "in", name: "India" },
  { code: "id", name: "Indonesia" }, { code: "ir", name: "Iran" },
  { code: "iq", name: "Iraq" }, { code: "ie", name: "Ireland" },
  { code: "im", name: "Isle of Man" }, { code: "il", name: "Israel" },
  { code: "it", name: "Italy" }, { code: "jm", name: "Jamaica" },
  { code: "jp", name: "Japan" }, { code: "je", name: "Jersey" },
  { code: "jo", name: "Jordan" }, { code: "kz", name: "Kazakhstan" },
  { code: "ke", name: "Kenya" }, { code: "ki", name: "Kiribati" },
  { code: "kw", name: "Kuwait" }, { code: "kg", name: "Kyrgyzstan" },
  { code: "la", name: "Laos" }, { code: "lv", name: "Latvia" },
  { code: "lb", name: "Lebanon" }, { code: "ls", name: "Lesotho" },
  { code: "lr", name: "Liberia" }, { code: "ly", name: "Libya" },
  { code: "li", name: "Liechtenstein" }, { code: "lt", name: "Lithuania" },
  { code: "lu", name: "Luxembourg" }, { code: "mo", name: "Macao" },
  { code: "mg", name: "Madagascar" }, { code: "mw", name: "Malawi" },
  { code: "my", name: "Malaysia" }, { code: "mv", name: "Maldives" },
  { code: "ml", name: "Mali" }, { code: "mt", name: "Malta" },
  { code: "mh", name: "Marshall Islands" }, { code: "mq", name: "Martinique" },
  { code: "mr", name: "Mauritania" }, { code: "mu", name: "Mauritius" },
  { code: "yt", name: "Mayotte" }, { code: "mx", name: "Mexico" },
  { code: "fm", name: "Micronesia" }, { code: "md", name: "Moldova" },
  { code: "mc", name: "Monaco" }, { code: "mn", name: "Mongolia" },
  { code: "me", name: "Montenegro" }, { code: "ms", name: "Montserrat" },
  { code: "ma", name: "Morocco" }, { code: "mz", name: "Mozambique" },
  { code: "mm", name: "Myanmar" }, { code: "na", name: "Namibia" },
  { code: "nr", name: "Nauru" }, { code: "np", name: "Nepal" },
  { code: "nl", name: "Netherlands" }, { code: "nc", name: "New Caledonia" },
  { code: "nz", name: "New Zealand" }, { code: "ni", name: "Nicaragua" },
  { code: "ne", name: "Niger" }, { code: "ng", name: "Nigeria" },
  { code: "nu", name: "Niue" }, { code: "mk", name: "North Macedonia" },
  { code: "no", name: "Norway" }, { code: "om", name: "Oman" },
  { code: "pk", name: "Pakistan" }, { code: "pw", name: "Palau" },
  { code: "ps", name: "Palestine" }, { code: "pa", name: "Panama" },
  { code: "pg", name: "Papua New Guinea" }, { code: "py", name: "Paraguay" },
  { code: "pe", name: "Peru" }, { code: "ph", name: "Philippines" },
  { code: "pl", name: "Poland" }, { code: "pt", name: "Portugal" },
  { code: "pr", name: "Puerto Rico" }, { code: "qa", name: "Qatar" },
  { code: "re", name: "Réunion" }, { code: "ro", name: "Romania" },
  { code: "ru", name: "Russia" }, { code: "rw", name: "Rwanda" },
  { code: "ws", name: "Samoa" }, { code: "sm", name: "San Marino" },
  { code: "st", name: "São Tomé and Príncipe" }, { code: "sa", name: "Saudi Arabia" },
  { code: "sn", name: "Senegal" }, { code: "rs", name: "Serbia" },
  { code: "sc", name: "Seychelles" }, { code: "sl", name: "Sierra Leone" },
  { code: "sg", name: "Singapore" }, { code: "sk", name: "Slovakia" },
  { code: "si", name: "Slovenia" }, { code: "sb", name: "Solomon Islands" },
  { code: "so", name: "Somalia" }, { code: "za", name: "South Africa" },
  { code: "kr", name: "South Korea" }, { code: "ss", name: "South Sudan" },
  { code: "es", name: "Spain" }, { code: "lk", name: "Sri Lanka" },
  { code: "kn", name: "St Kitts and Nevis" }, { code: "lc", name: "St Lucia" },
  { code: "vc", name: "St Vincent and the Grenadines" }, { code: "sd", name: "Sudan" },
  { code: "sr", name: "Suriname" }, { code: "se", name: "Sweden" },
  { code: "ch", name: "Switzerland" }, { code: "sy", name: "Syria" },
  { code: "tw", name: "Taiwan" }, { code: "tj", name: "Tajikistan" },
  { code: "tz", name: "Tanzania" }, { code: "th", name: "Thailand" },
  { code: "tl", name: "Timor-Leste" }, { code: "tg", name: "Togo" },
  { code: "to", name: "Tonga" }, { code: "tt", name: "Trinidad and Tobago" },
  { code: "tn", name: "Tunisia" }, { code: "tr", name: "Türkiye" },
  { code: "tm", name: "Turkmenistan" }, { code: "tc", name: "Turks and Caicos Islands" },
  { code: "tv", name: "Tuvalu" }, { code: "ug", name: "Uganda" },
  { code: "ua", name: "Ukraine" }, { code: "ae", name: "United Arab Emirates" },
  { code: "gb", name: "United Kingdom" }, { code: "us", name: "United States" },
  { code: "uy", name: "Uruguay" }, { code: "uz", name: "Uzbekistan" },
  { code: "vu", name: "Vanuatu" }, { code: "va", name: "Vatican City" },
  { code: "ve", name: "Venezuela" }, { code: "vn", name: "Vietnam" },
  { code: "vg", name: "Virgin Islands (British)" }, { code: "vi", name: "Virgin Islands (US)" },
  { code: "ye", name: "Yemen" }, { code: "zm", name: "Zambia" },
  { code: "zw", name: "Zimbabwe" },
];

export interface JurisdictionOption {
  value: string; // the code stored on the entity (legacy slug or ISO alpha-2)
  name: string;
  iso2: string; // for the flag
}

// Merge legacy JURISDICTIONS (slugs like "uk"/"uae") with the full ISO list,
// each country once, preferring the legacy slug so existing rows keep matching.
// "eu" (European Union) is carried from the legacy map — it's not an ISO country
// but flagcdn serves it and entities use it.
//
// Computed lazily + memoised: `JURISDICTIONS` is referenced only INSIDE this
// function (not at module top-level), which avoids the format.ts ↔ countries.ts
// import cycle blowing up during initialisation.
let _options: JurisdictionOption[] | null = null;
export function jurisdictionOptions(): JurisdictionOption[] {
  if (_options) return _options;
  const out: JurisdictionOption[] = [];
  const takenIso = new Set<string>();
  for (const [value, j] of Object.entries(JURISDICTIONS)) {
    out.push({ value, name: j.name, iso2: j.iso2 });
    if (j.iso2) takenIso.add(j.iso2);
  }
  for (const c of COUNTRIES) {
    if (takenIso.has(c.code)) continue; // already covered by a legacy slug
    out.push({ value: c.code, name: c.name, iso2: c.code });
  }
  _options = out.sort((a, b) => a.name.localeCompare(b.name));
  return _options;
}

const _NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  COUNTRIES.map((c) => [c.code, c.name]),
);

/** Resolve any code to a display name + iso2, covering the full country list
 *  (used by lib/format's jurisdiction() fallback so badges work everywhere). */
export function countryFor(code: string | null | undefined): { name: string; iso2: string } | null {
  const c = (code ?? "").toLowerCase();
  if (_NAME_BY_CODE[c]) return { name: _NAME_BY_CODE[c], iso2: c };
  return null;
}
