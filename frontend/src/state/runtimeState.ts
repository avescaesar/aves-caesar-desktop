import type { VersionDetails } from "../types";

const DETECTING_DEVICE_SENTINEL = "Detecting...";

export class RuntimeState {
	public provider = "";
	public device = "";
	public appVersion = "0.0.0";
	public versionDetails: VersionDetails | null = null;
	public appIconDataUrl: string | null = null;


	public applyDevice(provider: string, device: string): void {
		this.provider = provider;
		this.device = this.isDetecting(device) ? "" : device;
	}


	public startDeviceDetection(): void {
		this.provider = "";
		this.device = "";
	}


	public isDetecting(device = this.device): boolean {
		return !device || device === DETECTING_DEVICE_SENTINEL;
	}
}
