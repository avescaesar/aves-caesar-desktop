import { ActiveView } from "../../types";
import type { AppControllerContext } from "../core/appControllerContext";
import type { EventBinder } from "../core/eventBinder";
import type { ViewController } from "../view/viewController";

const NAVIGATION_DOM = {
	vertical: "navigation",
	entities: {
		detection: "detection",
		collection: "collection",
		organization: "organization",
		lightroom: "lightroom",
	},
	action: "show",
} as const;

export class ViewRouter {
	private readonly viewControllers: Map<ActiveView, ViewController>;


	public constructor(private readonly context: AppControllerContext, viewControllers: ViewController[]) {
		this.viewControllers = new Map(viewControllers.map(viewController => [viewController.view, viewController]));
	}


	public bindEvents(bindEvent: EventBinder): void {
		bindEvent(this.navigationButton(NAVIGATION_DOM.entities.detection), "click", () => void this.navigate(ActiveView.Detection));
		bindEvent(this.navigationButton(NAVIGATION_DOM.entities.collection), "click", () => void this.navigate(ActiveView.Collection));
		bindEvent(this.navigationButton(NAVIGATION_DOM.entities.organization), "click", () => void this.navigate(ActiveView.Organization));
		bindEvent(this.navigationButton(NAVIGATION_DOM.entities.lightroom), "click", () => void this.navigate(ActiveView.Lightroom));
	}


	private async navigate(view: ActiveView): Promise<void> {
		const nextViewController = this.viewControllers.get(view);
		if (!nextViewController) {
			return;
		}

		const currentView = this.context.state.navigation.activeView;
		if (currentView !== view) {
			const currentViewController = this.viewControllers.get(currentView);
			await currentViewController?.hide();
		}

		await nextViewController.show();
	}


	private navigationButton(entity: string): HTMLButtonElement | null {
		return document.querySelector<HTMLButtonElement>(`[data-vertical="${NAVIGATION_DOM.vertical}"][data-entity="${entity}"][data-action="${NAVIGATION_DOM.action}"]`);
	}
}
