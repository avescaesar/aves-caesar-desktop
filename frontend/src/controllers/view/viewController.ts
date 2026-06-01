import type { ActiveView } from "../../types";

export interface ViewController {
	readonly view: ActiveView;

	show(): Promise<void> | void;

	hide(): Promise<void> | void;
}
