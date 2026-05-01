import { Directive, Input, TemplateRef, ViewContainerRef, OnInit } from '@angular/core';
import { MenuService } from '../../core/services/menu.service';

@Directive({
  selector: '[hasPermission]',
  standalone: true,
})
export class HasPermissionDirective implements OnInit {
  @Input('hasPermission') permission = '';

  private hasView = false;

  constructor(
    private templateRef: TemplateRef<any>,
    private viewContainer: ViewContainerRef,
    private menuService: MenuService,
  ) {}

  ngOnInit(): void {
    this.updateView();
  }

  private updateView(): void {
    const [menuName, action] = this.permission.split(':');
    const allowed = this.menuService.hasPermission(menuName, action);

    if (allowed && !this.hasView) {
      this.viewContainer.createEmbeddedView(this.templateRef);
      this.hasView = true;
    } else if (!allowed && this.hasView) {
      this.viewContainer.clear();
      this.hasView = false;
    }
  }
}
