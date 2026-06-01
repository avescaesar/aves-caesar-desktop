import type { UpdateInfo, UpdateInstallStatus } from "../types";

export class UpdateState {
	public info: UpdateInfo | null = null;
	public promptOpen = false;
	public busy = false;
	public message = "";
	public installJobId: string | null = null;
	public installStatus: UpdateInstallStatus | null = null;


	public hasAvailableUpdate(): boolean {
		return this.info?.state === "available" && Boolean(this.info.availableVersion);
	}


	public shouldShowIndicator(): boolean {
		return this.hasAvailableUpdate();
	}
}
