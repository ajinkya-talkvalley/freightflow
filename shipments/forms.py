from django import forms

from .models import ShipmentStatus


class ShipmentFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Search tracking number',
        widget=forms.TextInput(attrs={'placeholder': 'FF-000001', 'class': 'form-control'}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses')] + list(ShipmentStatus.choices),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
