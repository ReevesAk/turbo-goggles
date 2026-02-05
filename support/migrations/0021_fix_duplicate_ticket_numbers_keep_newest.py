"""Django migration to fix duplicate Ticket.number values by keeping the newest
ticket (by created_at) and renaming older duplicates with a short suffix.

This is safer than deleting rows and keeps ticket history intact.
"""

from django.db import migrations, models


def resolve_duplicates_keep_newest(apps, schema_editor):
    Ticket = apps.get_model('support', 'Ticket')

    duplicate_numbers = (
        Ticket.objects.values('number')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
        .values_list('number', flat=True)
    )

    for number in duplicate_numbers:
        # Order by created_at desc so the newest ticket is first (to keep)
        tickets = list(Ticket.objects.filter(number=number).order_by('-created_at', '-id'))
        if not tickets:
            continue

        # tickets[0] is the newest; rename the rest
        base = str(number or "UNK")
        for i, ticket in enumerate(tickets[1:], start=1):
            # Try incremental suffixes until we find a free one
            attempt = 0
            while True:
                attempt += 1
                suffix = f"-D{i}" if attempt == 1 else f"-D{i}-{attempt}"
                max_len = 50 - len(suffix)
                truncated = base[:max_len]
                new_number = f"{truncated}{suffix}"

                # Ensure we don't collide with any existing ticket number
                exists = Ticket.objects.filter(number=new_number).exclude(pk=ticket.pk).exists()
                if not exists:
                    ticket.number = new_number
                    ticket.save(update_fields=['number'])
                    break
                # otherwise loop and try the next attempt


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0020_alter_ticket_number'),
    ]

    operations = [
        migrations.RunPython(resolve_duplicates_keep_newest),
    ]
