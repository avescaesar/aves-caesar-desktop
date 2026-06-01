import { NavigationState } from "./navigationState";
import { RuntimeState } from "./runtimeState";
import { SettingsState } from "./settingsState";
import { UpdateState } from "./updateState";

export class AppState {
	public readonly navigation = new NavigationState();
	public readonly runtime = new RuntimeState();
	public readonly settings = new SettingsState();
	public readonly update = new UpdateState();
}
