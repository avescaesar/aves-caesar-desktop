import { translate, type TranslationKey, type TranslationParams } from "../i18n/translations";
import type { SettingsState } from "../state/settingsState";

export class RendererContext {
	public constructor(private readonly settings: SettingsState) {}


	public text(key: TranslationKey, params: TranslationParams = {}): string {
		return translate(this.settings.appLanguage, key, params);
	}


	public locale(): string {
		return this.settings.appLanguage;
	}


	public languageName(language: string): string {
		try {
			const displayNamesConstructor = (Intl as typeof Intl & { DisplayNames?: new (locales: string[], options: { type: "language" }) => { of: (code: string) => string | undefined } }).DisplayNames;
			if (!displayNamesConstructor) {
				return language;
			}

			const displayNames = new displayNamesConstructor([this.locale()], { type: "language" });
			return displayNames.of(language) || language;
		} catch {
			return language;
		}
	}
}
