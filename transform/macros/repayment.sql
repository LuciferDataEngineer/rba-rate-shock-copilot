{% macro monthly_repayment(principal, annual_rate) %}
(
  case
    when {{ annual_rate }} is null then null
    when {{ annual_rate }} = 0 then {{ principal }} / 360.0
    else {{ principal }}
      * (({{ annual_rate }} / 100.0) / 12.0)
      * pow(1 + (({{ annual_rate }} / 100.0) / 12.0), 360)
      / (pow(1 + (({{ annual_rate }} / 100.0) / 12.0), 360) - 1)
  end
)
{% endmacro %}
