import type { ImageInfo, PredictResponse } from "../types";
import type { TranslationKey, TranslationParams } from "../i18n/translations";

export class DetectionState {
	public image: ImageInfo | null = null;
	public gpxPaths: string[] = [];
	public latitude = "";
	public longitude = "";
	public statusKey: TranslationKey = "status.selectImage";
	public statusParams: TranslationParams = {};
	public statusText = "";
	public loading = false;
	public activeJobId: string | null = null;
	public result: PredictResponse | null = null;


	public reset(): void {
		this.image = null;
		this.gpxPaths = [];
		this.latitude = "";
		this.longitude = "";
		this.setStatus("status.selectImage");
		this.loading = false;
		this.activeJobId = null;
		this.result = null;
	}


	public selectImage(image: ImageInfo): void {
		this.image = image;
		this.latitude = image.latitude == null ? "" : String(image.latitude);
		this.longitude = image.longitude == null ? "" : String(image.longitude);
		this.activeJobId = null;
		this.loading = false;
		this.result = null;
		this.setStatus(image.latitude != null && image.longitude != null ? "status.gpsFound" : "status.noGps");
	}


	public hasCoordinates(): boolean {
		return Boolean(this.latitude.trim() && this.longitude.trim());
	}


	public resultUsedCoordinates(): boolean {
		return this.result?.usedLatitude != null && this.result.usedLongitude != null;
	}


	public clearResult(): void {
		this.result = null;
	}


	public clearImageAndResult(): void {
		this.result = null;
		this.image = null;
	}


	public setStatus(key: TranslationKey, params: TranslationParams = {}): void {
		this.statusKey = key;
		this.statusParams = params;
		this.statusText = "";
	}


	public setRawStatus(text: string): void {
		this.statusText = text;
		this.statusParams = {};
	}
}
