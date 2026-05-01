import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule, MatSelectChange } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatTreeModule, MatTreeNestedDataSource } from '@angular/material/tree';
import { NestedTreeControl } from '@angular/cdk/tree';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';

interface CountryOption { countryid: number; countryname: string; }
interface StateOption { stateid: number; StateName: string; Country?: string; }
interface DistrictOption { districtid: number; districName: string; StateName?: string; Country?: string; }

interface TreeNode {
  name: string;
  type: 'country' | 'state' | 'district';
  id: number;
  children?: TreeNode[];
}

interface Mapping {
  countryid: number;
  countryName: string;
  stateid: number;
  stateName: string;
  districtid: number | null;
  districtName: string | null;
}

@Component({
  selector: 'app-user-location-dialog',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatDialogModule, MatFormFieldModule,
    MatSelectModule, MatButtonModule, MatIconModule, MatChipsModule,
    MatDividerModule, MatTreeModule, MatProgressSpinnerModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>Location Mapping — {{ data.userName }}</h2>
    <mat-dialog-content>
      <!-- Selection panel -->
      <div class="selection-panel">
        <div class="selection-row">
          <mat-form-field appearance="outline" class="sel-field">
            <mat-label>Country</mat-label>
            <mat-select [value]="selectedCountryIds" multiple
              (selectionChange)="onCountrySelect($event)"
              (openedChange)="onPanelToggle('country', $event)"
              panelClass="searchable-panel">
              <div class="select-search" (click)="$event.stopPropagation()">
                <mat-icon class="search-ico">search</mat-icon>
                <input #countrySearchInput placeholder="Search countries..."
                  (input)="countrySearch = asValue($event); filterCountries()"
                  (keydown)="$event.stopPropagation()">
              </div>
              <div class="select-all-row" (click)="toggleAllCountries(); $event.stopPropagation()">
                <mat-icon class="sa-icon">{{ isAllCountriesSelected() ? 'check_box' : (selectedCountryIds.length ? 'indeterminate_check_box' : 'check_box_outline_blank') }}</mat-icon>
                <span>Select All</span>
              </div>
              @for (c of displayedCountries; track c.countryid) {
                <mat-option [value]="c.countryid">{{ c.countryname }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="sel-field">
            <mat-label>State</mat-label>
            <mat-select [value]="selectedStateIds" multiple
              (selectionChange)="onStateSelect($event)"
              (openedChange)="onPanelToggle('state', $event)"
              [disabled]="!filteredStates.length"
              panelClass="searchable-panel">
              <div class="select-search" (click)="$event.stopPropagation()">
                <mat-icon class="search-ico">search</mat-icon>
                <input placeholder="Search states..."
                  (input)="stateSearch = asValue($event); filterStates()"
                  (keydown)="$event.stopPropagation()">
              </div>
              <div class="select-all-row" (click)="toggleAllStates(); $event.stopPropagation()">
                <mat-icon class="sa-icon">{{ isAllStatesSelected() ? 'check_box' : (selectedStateIds.length ? 'indeterminate_check_box' : 'check_box_outline_blank') }}</mat-icon>
                <span>Select All</span>
              </div>
              @for (s of displayedStates; track s.stateid) {
                <mat-option [value]="s.stateid">{{ s.StateName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="sel-field">
            <mat-label>District (optional)</mat-label>
            <mat-select [value]="selectedDistrictIds" multiple
              (selectionChange)="onDistrictSelect($event)"
              (openedChange)="onPanelToggle('district', $event)"
              [disabled]="!filteredDistricts.length"
              panelClass="searchable-panel">
              <div class="select-search" (click)="$event.stopPropagation()">
                <mat-icon class="search-ico">search</mat-icon>
                <input placeholder="Search districts..."
                  (input)="districtSearch = asValue($event); filterDistricts()"
                  (keydown)="$event.stopPropagation()">
              </div>
              <div class="select-all-row" (click)="toggleAllDistricts(); $event.stopPropagation()">
                <mat-icon class="sa-icon">{{ isAllDistrictsSelected() ? 'check_box' : (selectedDistrictIds.length ? 'indeterminate_check_box' : 'check_box_outline_blank') }}</mat-icon>
                <span>Select All</span>
              </div>
              @for (d of displayedDistricts; track d.districtid) {
                <mat-option [value]="d.districtid">{{ d.districName }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>

        <button mat-raised-button color="primary" (click)="addSelections()" class="add-btn"
          [disabled]="!selectedStateIds.length">
          <mat-icon>add</mat-icon> Add to Mapping
        </button>
      </div>

      <mat-divider></mat-divider>

      <!-- Current mapping tree -->
      <div class="tree-section">
        <h3>Assigned Locations</h3>
        @if (treeData.length === 0) {
          <p class="no-data">No locations assigned yet.</p>
        }
        <mat-tree [dataSource]="treeDataSource" [treeControl]="treeControl">
          <!-- Leaf node -->
          <mat-tree-node *matTreeNodeDef="let node" matTreeNodePadding>
            <span class="tree-leaf">
              <mat-icon class="tree-icon" [ngClass]="node.type">
                {{ node.type === 'district' ? 'location_on' : (node.type === 'state' ? 'map' : 'public') }}
              </mat-icon>
              {{ node.name }}
              <button mat-icon-button class="remove-btn" (click)="removeNode(node)" matTooltip="Remove">
                <mat-icon>close</mat-icon>
              </button>
            </span>
          </mat-tree-node>
          <!-- Parent node (country/state with children) -->
          <mat-nested-tree-node *matTreeNodeDef="let node; when: hasChildren">
            <div class="tree-parent">
              <button mat-icon-button matTreeNodeToggle>
                <mat-icon>{{ treeControl.isExpanded(node) ? 'expand_more' : 'chevron_right' }}</mat-icon>
              </button>
              <mat-icon class="tree-icon" [ngClass]="node.type">
                {{ node.type === 'country' ? 'public' : 'map' }}
              </mat-icon>
              <span>{{ node.name }}</span>
              <button mat-icon-button class="remove-btn" (click)="removeNode(node)" matTooltip="Remove all">
                <mat-icon>close</mat-icon>
              </button>
            </div>
            <div [class.tree-hidden]="!treeControl.isExpanded(node)">
              <ng-container matTreeNodeOutlet></ng-container>
            </div>
          </mat-nested-tree-node>
        </mat-tree>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="saving">
        @if (saving) { <mat-spinner diameter="18"></mat-spinner> }
        Save
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    mat-dialog-content { max-height: 70vh; }
    .selection-panel { padding: 1rem 0; }
    .selection-row {
      display: flex; gap: 0.75rem;
    }
    .sel-field { flex: 1; min-width: 0; }
    .add-btn { margin-bottom: 0.5rem; }
    mat-divider { margin: 0.5rem 0; }
    .tree-section { padding: 0.5rem 0; max-height: 35vh; overflow-y: auto; }
    .tree-section h3 { font-size: 14px; font-weight: 600; margin: 0 0 0.5rem 0; color: var(--snm-text-primary); }
    .no-data { text-align: center; color: var(--snm-text-muted); font-size: 13px; padding: 1rem 0; }
    .tree-parent {
      display: flex; align-items: center; gap: 4px;
      font-size: 14px; font-weight: 500; color: var(--snm-text-primary);
    }
    .tree-leaf {
      display: flex; align-items: center; gap: 4px; padding-left: 8px;
      font-size: 13px; color: var(--snm-text-secondary);
    }
    .tree-icon { font-size: 18px; width: 18px; height: 18px; line-height: 18px; }
    .tree-icon.country { color: var(--snm-accent); }
    .tree-icon.state { color: #4caf50; }
    .tree-icon.district { color: #ff9800; }
    .remove-btn { margin-left: auto; }
    .remove-btn mat-icon { font-size: 16px; width: 16px; height: 16px; color: var(--snm-error); }
    .tree-hidden { display: none; }

    /* Search & Select All inside mat-select panels */
    .select-search {
      display: flex; align-items: center; gap: 6px;
      padding: 8px 16px; border-bottom: 1px solid var(--snm-border-divider, #e0e0e0);
      position: sticky; top: 0; background: var(--snm-bg-card, #fff); z-index: 1;
    }
    .select-search input {
      border: none; outline: none; flex: 1; font-size: 14px;
      background: transparent; color: var(--snm-text-primary, #333);
    }
    .search-ico { font-size: 20px; width: 20px; height: 20px; color: var(--snm-text-muted, #888); }
    .select-all-row {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 16px; cursor: pointer;
      border-bottom: 1px solid var(--snm-border-divider, #e0e0e0);
      font-size: 14px; font-weight: 500; color: var(--snm-text-primary, #333);
    }
    .select-all-row:hover { background: rgba(0,0,0,0.04); }
    .sa-icon { font-size: 20px; width: 20px; height: 20px; color: var(--snm-accent, #1976d2); }
  `],
})
export class UserLocationDialogComponent implements OnInit {
  // Master data
  countries: CountryOption[] = [];
  allStates: StateOption[] = [];
  allDistricts: DistrictOption[] = [];
  filteredStates: StateOption[] = [];
  filteredDistricts: DistrictOption[] = [];

  // Displayed (search-filtered) options
  displayedCountries: CountryOption[] = [];
  displayedStates: StateOption[] = [];

  // Search terms
  countrySearch = '';
  stateSearch = '';
  districtSearch = '';

  // Selections
  selectedCountryIds: number[] = [];
  selectedStateIds: number[] = [];
  selectedDistrictIds: number[] = [];

  // Flat mappings (source of truth)
  mappings: Mapping[] = [];

  // Tree display
  treeData: TreeNode[] = [];
  treeDataSource = new MatTreeNestedDataSource<TreeNode>();
  treeControl = new NestedTreeControl<TreeNode>(node => node.children);

  saving = false;

  constructor(
    private api: ApiService,
    private notify: NotificationService,
    public dialogRef: MatDialogRef<UserLocationDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { userId: number; userName: string },
  ) {}

  hasChildren = (_: number, node: TreeNode) => !!node.children && node.children.length > 0;

  asValue(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  ngOnInit(): void {
    this.api.get<CountryOption[]>('/masters/countries').subscribe(d => {
      this.countries = d;
      this.displayedCountries = d;
    });
    this.api.get<StateOption[]>('/masters/states').subscribe(d => this.allStates = d);
    this.api.get<DistrictOption[]>('/masters/districts').subscribe(d => this.allDistricts = d);

    this.api.get<{ locations: any[] }>(`/users/${this.data.userId}/location-mappings`).subscribe({
      next: (res) => {
        for (const country of res.locations) {
          for (const state of country.states) {
            if (state.districts && state.districts.length > 0) {
              for (const district of state.districts) {
                this.mappings.push({
                  countryid: country.countryid,
                  countryName: country.countryName,
                  stateid: state.stateid,
                  stateName: state.stateName,
                  districtid: district.districtid,
                  districtName: district.districtName,
                });
              }
            } else {
              // State-level mapping (no district)
              this.mappings.push({
                countryid: country.countryid,
                countryName: country.countryName,
                stateid: state.stateid,
                stateName: state.stateName,
                districtid: null,
                districtName: null,
              });
            }
          }
        }
        this.rebuildTree();
      },
    });
  }

  // --- Panel open/close: reset search ---
  onPanelToggle(type: string, opened: boolean): void {
    if (!opened) return;
    if (type === 'country') { this.countrySearch = ''; this.filterCountries(); }
    if (type === 'state') { this.stateSearch = ''; this.filterStates(); }
    if (type === 'district') { this.districtSearch = ''; this.filterDistricts(); }
  }

  // --- Country ---
  filterCountries(): void {
    const term = this.countrySearch.toLowerCase();
    this.displayedCountries = term
      ? this.countries.filter(c => c.countryname.toLowerCase().includes(term))
      : [...this.countries];
  }

  isAllCountriesSelected(): boolean {
    return this.displayedCountries.length > 0
      && this.displayedCountries.every(c => this.selectedCountryIds.includes(c.countryid));
  }

  toggleAllCountries(): void {
    if (this.isAllCountriesSelected()) {
      const displayedIds = new Set(this.displayedCountries.map(c => c.countryid));
      this.selectedCountryIds = this.selectedCountryIds.filter(id => !displayedIds.has(id));
    } else {
      const existing = new Set(this.selectedCountryIds);
      for (const c of this.displayedCountries) existing.add(c.countryid);
      this.selectedCountryIds = [...existing];
    }
    this.onCountriesChange();
  }

  onCountrySelect(event: MatSelectChange): void {
    this.selectedCountryIds = event.value;
    this.onCountriesChange();
  }

  private onCountriesChange(): void {
    const countryNames = this.countries
      .filter(c => this.selectedCountryIds.includes(c.countryid))
      .map(c => c.countryname);

    this.filteredStates = this.allStates.filter(s => countryNames.includes(s.Country || ''));
    this.displayedStates = [...this.filteredStates];
    this.selectedStateIds = this.selectedStateIds.filter(
      id => this.filteredStates.some(s => s.stateid === id),
    );
    this.onStatesChange();
  }

  // --- State ---
  filterStates(): void {
    const term = this.stateSearch.toLowerCase();
    this.displayedStates = term
      ? this.filteredStates.filter(s => s.StateName.toLowerCase().includes(term))
      : [...this.filteredStates];
  }

  isAllStatesSelected(): boolean {
    return this.displayedStates.length > 0
      && this.displayedStates.every(s => this.selectedStateIds.includes(s.stateid));
  }

  toggleAllStates(): void {
    if (this.isAllStatesSelected()) {
      const displayedIds = new Set(this.displayedStates.map(s => s.stateid));
      this.selectedStateIds = this.selectedStateIds.filter(id => !displayedIds.has(id));
    } else {
      const existing = new Set(this.selectedStateIds);
      for (const s of this.displayedStates) existing.add(s.stateid);
      this.selectedStateIds = [...existing];
    }
    this.onStatesChange();
  }

  onStateSelect(event: MatSelectChange): void {
    this.selectedStateIds = event.value;
    this.onStatesChange();
  }

  private onStatesChange(): void {
    const stateNames = this.allStates
      .filter(s => this.selectedStateIds.includes(s.stateid))
      .map(s => s.StateName);

    this.filteredDistricts = this.allDistricts.filter(d => stateNames.includes(d.StateName || ''));
    this.displayedDistricts = [...this.filteredDistricts];
    this.selectedDistrictIds = this.selectedDistrictIds.filter(
      id => this.filteredDistricts.some(d => d.districtid === id),
    );
  }

  // Displayed (search-filtered) districts
  displayedDistricts: DistrictOption[] = [];

  // --- District ---
  filterDistricts(): void {
    const term = this.districtSearch.toLowerCase();
    this.displayedDistricts = term
      ? this.filteredDistricts.filter(d => d.districName.toLowerCase().includes(term))
      : [...this.filteredDistricts];
  }

  isAllDistrictsSelected(): boolean {
    return this.filteredDistricts.length > 0
      && this.filteredDistricts.every(d => this.selectedDistrictIds.includes(d.districtid));
  }

  toggleAllDistricts(): void {
    if (this.isAllDistrictsSelected()) {
      const displayedIds = new Set(this.filteredDistricts.map(d => d.districtid));
      this.selectedDistrictIds = this.selectedDistrictIds.filter(id => !displayedIds.has(id));
    } else {
      const existing = new Set(this.selectedDistrictIds);
      for (const d of this.filteredDistricts) existing.add(d.districtid);
      this.selectedDistrictIds = [...existing];
    }
  }

  onDistrictSelect(event: MatSelectChange): void {
    this.selectedDistrictIds = event.value;
  }

  // --- Add selections to mappings ---
  addSelections(): void {
    if (this.selectedDistrictIds.length > 0) {
      // Add one mapping per selected district
      for (const did of this.selectedDistrictIds) {
        if (this.mappings.some(m => m.districtid === did)) continue;

        const district = this.allDistricts.find(d => d.districtid === did);
        if (!district) continue;
        const state = this.allStates.find(s => s.StateName === district.StateName && s.Country === district.Country);
        if (!state) continue;
        const country = this.countries.find(c => c.countryname === district.Country);
        if (!country) continue;

        this.mappings.push({
          countryid: country.countryid, countryName: country.countryname,
          stateid: state.stateid, stateName: state.StateName,
          districtid: district.districtid, districtName: district.districName,
        });
      }
    } else {
      // No districts selected — add state-level mappings
      for (const sid of this.selectedStateIds) {
        if (this.mappings.some(m => m.stateid === sid && m.districtid === null)) continue;

        const state = this.allStates.find(s => s.stateid === sid);
        if (!state) continue;
        const country = this.countries.find(c => c.countryname === state.Country);
        if (!country) continue;

        this.mappings.push({
          countryid: country.countryid, countryName: country.countryname,
          stateid: state.stateid, stateName: state.StateName,
          districtid: null, districtName: null,
        });
      }
    }

    this.selectedCountryIds = [];
    this.selectedStateIds = [];
    this.selectedDistrictIds = [];
    this.filteredStates = [];
    this.filteredDistricts = [];
    this.displayedCountries = [...this.countries];
    this.displayedStates = [];

    this.rebuildTree();
  }

  // --- Remove ---
  removeNode(node: TreeNode): void {
    if (node.type === 'district') {
      this.mappings = this.mappings.filter(m => m.districtid !== node.id);
    } else if (node.type === 'state') {
      this.mappings = this.mappings.filter(m => m.stateid !== node.id);
    } else if (node.type === 'country') {
      this.mappings = this.mappings.filter(m => m.countryid !== node.id);
    }
    this.rebuildTree();
  }

  // --- Tree ---
  private rebuildTree(): void {
    const countryMap = new Map<number, TreeNode>();

    for (const m of this.mappings) {
      if (!countryMap.has(m.countryid)) {
        countryMap.set(m.countryid, {
          name: m.countryName, type: 'country', id: m.countryid, children: [],
        });
      }
      const countryNode = countryMap.get(m.countryid)!;
      let stateNode = countryNode.children!.find(s => s.id === m.stateid);

      if (m.districtid !== null) {
        // District-level mapping
        if (!stateNode) {
          stateNode = { name: m.stateName, type: 'state', id: m.stateid, children: [] };
          countryNode.children!.push(stateNode);
        }
        if (!stateNode.children!.some(d => d.id === m.districtid)) {
          stateNode.children!.push({
            name: m.districtName!, type: 'district', id: m.districtid,
          });
        }
      } else {
        // State-level mapping (no district) — state is a leaf
        if (!stateNode) {
          stateNode = { name: m.stateName, type: 'state', id: m.stateid };
          countryNode.children!.push(stateNode);
        }
      }
    }

    this.treeData = Array.from(countryMap.values());
    this.treeDataSource.data = this.treeData;

    for (const node of this.treeData) {
      this.treeControl.expand(node);
      for (const child of node.children || []) {
        this.treeControl.expand(child);
      }
    }
  }

  // --- Save ---
  save(): void {
    this.saving = true;
    const payload = this.mappings.map(m => ({
      countryid: m.countryid,
      stateid: m.stateid,
      districtid: m.districtid,
    }));

    this.api.post(`/users/${this.data.userId}/location-mappings`, payload).subscribe({
      next: () => {
        this.notify.success('Location mappings saved');
        this.dialogRef.close(true);
      },
      error: () => {
        this.notify.error('Failed to save location mappings');
        this.saving = false;
      },
    });
  }
}
