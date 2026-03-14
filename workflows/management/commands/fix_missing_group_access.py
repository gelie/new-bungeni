"""
Management command to fix workflows that are missing WorkflowGroupAccess records.
This can happen if workflows were created through code paths that don't call add_group_access().
"""

from django.core.management.base import BaseCommand
from workflows.models import Workflow, WorkflowGroupAccess


class Command(BaseCommand):
    help = 'Fix workflows missing WorkflowGroupAccess records by creating them from WorkflowType.group'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find workflows without any group access
        workflows_without_access = Workflow.objects.filter(
            group_access__isnull=True
        ).select_related('workflow_type', 'workflow_type__group', 'owner')
        
        count = workflows_without_access.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✓ All workflows have group access configured'))
            return
        
        self.stdout.write(
            self.style.WARNING(f'Found {count} workflow(s) without group access:')
        )
        
        fixed = 0
        for workflow in workflows_without_access:
            self.stdout.write(
                f'\n  - ID {workflow.id}: "{workflow.title}"'
            )
            self.stdout.write(
                f'    Type: {workflow.workflow_type.name}'
            )
            self.stdout.write(
                f'    Owner: {workflow.owner.get_full_name() or workflow.owner.username}'
            )
            self.stdout.write(
                f'    Created: {workflow.created_at}'
            )
            
            # Determine which group to assign
            target_group = workflow.workflow_type.group
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'    Would create access for: {target_group.name}'
                    )
                )
            else:
                # Create the group access
                access = workflow.add_group_access(
                    group=target_group,
                    is_primary=True,
                    granted_by=None,  # System-generated
                    notes=f"Auto-created by fix_missing_group_access command - inherited from WorkflowType.group"
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'    ✓ Created access for: {target_group.name}'
                    )
                )
                fixed += 1
        
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\nDRY RUN: Would fix {count} workflow(s)'
                )
            )
            self.stdout.write(
                'Run without --dry-run to apply changes'
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Successfully fixed {fixed} workflow(s)'
                )
            )
