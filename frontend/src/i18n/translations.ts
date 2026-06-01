import lang_en from "./en.json";
import type { AppLanguage } from "../types";

export type TranslationKey = keyof typeof lang_en;
export type TranslationParams = Record<string, number | string>;
type TranslationSet = Partial<Record<TranslationKey, string>>;
type TranslationModule = { default: TranslationSet };

export const AVAILABLE_APP_LANGUAGES: AppLanguage[] = ["en", "fr", "es", "de"];

const TRANSLATION_LOADERS = import.meta.glob<TranslationModule>(["./*.json", "!./en.json"]);
const TRANSLATIONS: Record<string, TranslationSet> = {
	en: lang_en,
};


export async function loadTranslations(language: AppLanguage): Promise<void> {
	const normalizedLanguage = normalizeTranslationLanguage(language);
	if (!AVAILABLE_APP_LANGUAGES.includes(normalizedLanguage)) {
		return;
	}

	if (TRANSLATIONS[normalizedLanguage]) {
		return;
	}

	const loader = TRANSLATION_LOADERS[`./${normalizedLanguage}.json`];
	if (!loader) {
		return;
	}

	const module = await loader();
	TRANSLATIONS[normalizedLanguage] = module.default;
}


export function translate(language: AppLanguage, key: TranslationKey, params: TranslationParams = {}): string {
	const normalizedLanguage = normalizeTranslationLanguage(language);
	let text = TRANSLATIONS[normalizedLanguage]?.[key] ?? TRANSLATIONS.en?.[key] ?? key;
	Object.entries(params).forEach(([name, value]) => {
		text = text.split(`{${name}}`).join(String(value));
	});
	return text;
}


function normalizeTranslationLanguage(language: AppLanguage): AppLanguage {
	return String(language || "en").toLowerCase().split("-", 1)[0];
}
