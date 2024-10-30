# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import Product, FmcgRating, PickupAdress, FmcgOrder


class ProductSerializers(serializers.ModelSerializer):
    """Serializers for creating an FMCG product."""
    image_url = serializers.FileField(max_length=155)
    additional_images = serializers.FileField(max_length=155, required=False)
    subtitle = serializers.CharField(max_length=250, required=False)
    input_style = serializers.CharField(max_length=250, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "image_url",
            "name_and_size",
            "category",
            "price",
            "expiry_date",
            "description",
            "macro_nutrients",
            "micro_nutrients",
            "density",
            "calories",
            "moisture",
            "texture",
            "storage",
            "additional_images",
            "subtitle",
            "input_style",
        ]


class AddToCartSerializers(serializers.ModelSerializer):
    """Serializers for adding a product an FMCG product to cart."""

    class Meta:
        model = Product
        fields = [
            "id",
            "quantity"
        ]


class AddFmcgPickupAddressSerializers(serializers.ModelSerializer):
    class Meta:
        model = PickupAdress
        fields = [
            "name",
            "state"
        ]


class RetrieveCartProductsSerializers(serializers.Serializer):
    """Serializers for retrieving cart products."""
    message = serializers.CharField(max_length=200)


class RemoveFromCartSerializers(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class FmcgOrderSerializer(serializers.ModelSerializer):
    pin = serializers.CharField(max_length=4, min_length=4)
    payment_method = serializers.CharField(max_length=4, min_length=4)

    class Meta:
        model = FmcgOrder
        fields = [
            "payment_option",
            "billing_address",
            "available_addresses",
            "product",
            "delivery_address",
            "status",
            "total_price",
            "pin"
        ]

    def __init__(self, *args, **kwargs):
        super(FmcgOrderSerializer, self).__init__(*args, **kwargs)

        request_data = self.context.get('request').data

        # Conditionally make fields optional based on billing_address
        billing_address = request_data.get('billing_address')

        if billing_address == "Store Pick-Up":
            self.fields['available_addresses'].required = True
        elif billing_address == "Delivery":
            self.fields['delivery_address'].required = True


class FmcgRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FmcgRating
        fields = [
            "id",
            "rating",
            "review",
        ]


class FmcgRatingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FmcgRating
        fields = [
            "id",
            "product",
            "rating",
            "review",
        ]
