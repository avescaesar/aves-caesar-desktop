import type { BirdName, AppLanguage } from "../types";

type BirdNamesLoader = (language: AppLanguage) => Promise<BirdName[]>;

export class SpeciesCorrectionState {
	public birdNames: BirdName[] = [];
	public birdNamesLanguage: AppLanguage = "";
	public editingBirdIndex: number | null = null;
	public speciesSearchQuery = "";
	public busy = false;
	public error = "";
	private readonly birdNamesByLanguage = new Map<AppLanguage, BirdName[]>();
	private readonly pendingBirdNamesByLanguage = new Map<AppLanguage, Promise<BirdName[]>>();


	public openEditor(birdIndex: number): void {
		this.editingBirdIndex = birdIndex;
		this.speciesSearchQuery = "";
		this.error = "";
	}


	public closeEditor(): void {
		this.editingBirdIndex = null;
		this.speciesSearchQuery = "";
		this.busy = false;
		this.error = "";
	}


	public resetCurrentBirdNames(): void {
		this.birdNames = [];
		this.birdNamesLanguage = "";
	}


	public async loadBirdNamesForLanguage(language: AppLanguage, loader: BirdNamesLoader): Promise<BirdName[]> {
		const cachedBirdNames = this.birdNamesByLanguage.get(language);
		if (cachedBirdNames) {
			this.applyBirdNames(language, cachedBirdNames);
			return cachedBirdNames;
		}

		const pendingBirdNames = this.pendingBirdNamesByLanguage.get(language);
		if (pendingBirdNames) {
			const birdNames = await pendingBirdNames;
			this.applyBirdNames(language, birdNames);
			return birdNames;
		}

		const request = loader(language);
		this.pendingBirdNamesByLanguage.set(language, request);
		try {
			const birdNames = await request;
			this.birdNamesByLanguage.set(language, birdNames);
			this.applyBirdNames(language, birdNames);
			return birdNames;
		} finally {
			this.pendingBirdNamesByLanguage.delete(language);
		}
	}


	private applyBirdNames(language: AppLanguage, birdNames: BirdName[]): void {
		this.birdNames = birdNames;
		this.birdNamesLanguage = language;
	}
}
