import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'searchFilter', standalone: true })
export class SearchFilterPipe implements PipeTransform {
  transform(items: any[], search: string, field: string): any[] {
    if (!items || !search) return items || [];
    const term = search.toLowerCase();
    return items.filter(item => (item[field] || '').toLowerCase().includes(term));
  }
}
